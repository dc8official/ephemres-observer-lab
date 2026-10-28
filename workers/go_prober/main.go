// go_prober - the Go (goroutines) engine of the Observer-Effect lab.
//
// It replicates probe_lab.py (--jsonl mode) mechanic for mechanic so the three
// engines can be compared like for like, and it speaks the same NDJSON protocol
// on stdout (events: start, cycle, tick, summary) so the dashboard needs no
// engine-specific code.
//
// THE TWO CLOCKS (same as Python and Rust)
//
//	Clock A  kernel arrival time of the reply, delivered as a control message
//	         (cmsg) alongside the packet by recvmsg().
//	Clock B  time.Now() taken in Go the instant recvmsg() returns.
//	observer lag = B - A  = how long the reply waited for this program to read it.
//
// HOW GO DIFFERS FROM PYTHON HERE
//
//	Python: one thread, one event loop. Anything that runs (the ORM spin)
//	        blocks the socket reader completely.
//	Go:     many goroutines, run by at most GOMAXPROCS OS threads at a time. The socket
//	        reader is just another goroutine. With GOMAXPROCS=1 ("single_core")
//	        it competes with the ORM-spinning goroutines for the one thread,
//	        and the runtime can only interrupt a spinning goroutine by async
//	        preemption (~10 ms time slice). With more threads ("multi_core")
//	        the reader runs on another thread while the ORM spin burns here.
//
// Build: see ../../build_workers.sh   (standard library only, no cgo).
package main

import (
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"net"
	"os"
	"os/exec"
	"os/signal"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

// ---------------------------------------------------------------------------
// Linux constants not exported by package syscall.
// ---------------------------------------------------------------------------
const (
	soTimestamping   = 37 // setsockopt option: SO_TIMESTAMPING
	soTimestampNS    = 35 // older, simpler: SO_TIMESTAMPNS
	soRcvbufForce    = 33 // SO_RCVBUFFORCE: set the receive queue size ignoring net.core.rmem_max (root)
	scmTimestamping  = 37 // cmsg type carrying struct scm_timestamping (3 x timespec)
	scmTimestampNS   = 35 // cmsg type carrying one struct timespec
	solRaw           = 255
	icmpFilterOpt    = 1 // struct icmp_filter { u32 data }: bit N set => BLOCK ICMP type N
	sofRxSoftware    = 1 << 3
	sofSoftware      = 1 << 4
	icmpEchoReply    = 0
	icmpEchoRequest  = 8
	payloadLen       = 56
	canaryTick       = 10 * time.Millisecond
	canaryMaxSamples = 120000
)

// ---------------------------------------------------------------------------
// ICMP packet building (identical bytes to the Python and Rust engines)
// ---------------------------------------------------------------------------

// icmpChecksum is the RFC 1071 Internet checksum: one's-complement sum of
// 16-bit big-endian words. A raw ICMP socket adds the IP header for us but not this.
func icmpChecksum(b []byte) uint16 {
	var sum uint32
	for i := 0; i+1 < len(b); i += 2 {
		sum += uint32(binary.BigEndian.Uint16(b[i:]))
	}
	if len(b)%2 == 1 {
		sum += uint32(b[len(b)-1]) << 8
	}
	for sum>>16 != 0 {
		sum = (sum & 0xffff) + (sum >> 16)
	}
	return ^uint16(sum)
}

// buildEchoRequest = type 8, code 0, checksum, id, seq, then 56 payload bytes.
// RFC 792 obliges every responder to echo id+seq back: that is the "return
// address" that lets one socket serve hundreds of virtual endpoints.
func buildEchoRequest(id, seq uint16) []byte {
	pkt := make([]byte, 8+payloadLen)
	pkt[0] = icmpEchoRequest
	binary.BigEndian.PutUint16(pkt[4:], id)
	binary.BigEndian.PutUint16(pkt[6:], seq)
	payload := pkt[8:]
	copy(payload, "EPHEMRES")
	binary.BigEndian.PutUint16(payload[8:], id)
	binary.BigEndian.PutUint16(payload[10:], seq)
	for i := 12; i < payloadLen; i++ {
		payload[i] = 0xa5
	}
	binary.BigEndian.PutUint16(pkt[2:], icmpChecksum(pkt))
	return pkt
}

// ---------------------------------------------------------------------------
// Scheduler canary: "wake me in 10 ms", measure how late we really wake.
// ---------------------------------------------------------------------------
type canarySample struct {
	start, end int64   // monotonic ns since process start
	lagUs      float64 // lateness in microseconds
}

// canary is a goroutine that sleeps 10 ms in a loop and records how late each wake-up was.
// Lateness means the Go scheduler had no free slot for it: the same delay the socket reader suffers.
type canary struct {
	mu      sync.Mutex
	base    time.Time
	samples []canarySample
	epoch   int64 // ticks that began before this are ignored (startup)
	frozen  bool  // closed gate: teardown / summary work is not measured
	maxAll  float64
	stop    atomic.Bool
}

func (c *canary) nowNs() int64 { return int64(time.Since(c.base)) } // monotonic clock

// run is the canary loop; it ends when stop is set.
func (c *canary) run() {
	for !c.stop.Load() {
		t0 := c.nowNs()
		time.Sleep(canaryTick)
		t1 := c.nowNs()
		c.mu.Lock()
		if !c.frozen && t0 >= c.epoch {
			lag := math.Max(0, float64(t1-t0-int64(canaryTick))/1000)
			c.samples = append(c.samples, canarySample{t0, t1, lag})
			if len(c.samples) > canaryMaxSamples {
				c.samples = append([]canarySample(nil), c.samples[canaryMaxSamples/2:]...)
			}
			if lag > c.maxAll {
				c.maxAll = lag
			}
		}
		c.mu.Unlock()
	}
}

// reset opens the measurement gate (call once startup/warm-up is finished).
func (c *canary) reset() {
	c.mu.Lock()
	c.samples, c.maxAll, c.frozen = nil, 0, false
	c.epoch = c.nowNs()
	c.mu.Unlock()
}

// freeze closes the gate (call before teardown and summary formatting).
func (c *canary) freeze() { c.mu.Lock(); c.frozen = true; c.mu.Unlock() }

// canaryStats is the canary summary sent to the dashboard (same field names in all three engines).
type canaryStats struct {
	Avg     float64 `json:"avg_lag_us"`
	P95     float64 `json:"p95_lag_us"`
	Max     float64 `json:"max_lag_us"`
	Samples int     `json:"samples"`
}

// r1 rounds to one decimal, for compact JSON.
func r1(x float64) float64 { return math.Round(x*10) / 10 }

// summarise turns a list of canary lateness samples (µs) into average, p95 and max.
func summarise(lags []float64) canaryStats {
	if len(lags) == 0 {
		return canaryStats{}
	}
	sort.Float64s(lags)
	var sum float64
	for _, v := range lags {
		sum += v
	}
	pos := float64(len(lags)-1) * 0.95 // linear-interpolated percentile (numpy default)
	lo := int(pos)
	hi := lo + 1
	if hi >= len(lags) {
		hi = len(lags) - 1
	}
	p95 := lags[lo] + (lags[hi]-lags[lo])*(pos-float64(lo))
	return canaryStats{r1(sum / float64(len(lags))), r1(p95), r1(lags[len(lags)-1]), len(lags)}
}

// window returns stats of ticks overlapping [start,end]; walks newest-first and stops early.
func (c *canary) window(start, end int64) canaryStats {
	c.mu.Lock()
	defer c.mu.Unlock()
	var lags []float64
	for i := len(c.samples) - 1; i >= 0; i-- {
		s := c.samples[i]
		if s.end < start {
			break
		}
		if s.start <= end {
			lags = append(lags, s.lagUs)
		}
	}
	return summarise(lags)
}

// all summarises every canary sample of the run.
func (c *canary) all() canaryStats {
	c.mu.Lock()
	defer c.mu.Unlock()
	lags := make([]float64, len(c.samples))
	for i, s := range c.samples {
		lags[i] = s.lagUs
	}
	return summarise(lags)
}

// ---------------------------------------------------------------------------
// The shared raw socket + reply demultiplexer
// ---------------------------------------------------------------------------
type pending struct {
	id, seq uint16
	tx      int64 // CLOCK_REALTIME ns just before sendto
	done    chan struct{}
	got     bool  // set by the reader before closing done
	krx     int64 // Clock A (0 = none)
	urx     int64 // Clock B
	batch   int
	wakeup  int64
	hasK    bool
}

// prober owns the raw ICMP socket and the table of pings waiting for a reply,
// keyed by (icmp_id, icmp_seq), plus the run's counters.
type prober struct {
	fd      int
	file    *os.File
	rc      syscall.RawConn
	mu      sync.Mutex
	pending map[uint32]*pending
	// Pings that timed out, kept so a reply that turns up later is recognised as LATE (with its
	// kernel stamp) rather than lumped in with other programs' pings. A late reply whose Clock A
	// is still inside the timeout was "lost" only because this program read it too late.
	expired map[uint32]*pending

	sent, replied, wakeups, unmatched, late atomic.Int64

	emitMu sync.Mutex
	emitNs atomic.Int64
	emitN  atomic.Int64
	clock  string
	notes  []string
}

// open creates the raw ICMP socket with kernel receive timestamps and a large receive queue.
func (p *prober) open() error {
	// SOCK_NONBLOCK lets Go's network poller (epoll) manage the descriptor, so a
	// goroutine waiting for a reply is parked instead of occupying an OS thread.
	fd, err := syscall.Socket(syscall.AF_INET, syscall.SOCK_RAW|syscall.SOCK_NONBLOCK|syscall.SOCK_CLOEXEC, syscall.IPPROTO_ICMP)
	if err != nil {
		return fmt.Errorf("raw ICMP socket: %w (need root or cap_net_raw)", err)
	}
	// Deliver only Echo Replies. Bit N set => block type N.
	filter := ^uint32(1 << icmpEchoReply) // variable, not constant: it must wrap into an int32
	_ = syscall.SetsockoptInt(fd, solRaw, icmpFilterOpt, int(int32(filter)))
	// Big receive queue: while this program is busy, replies pile up in the kernel. A plain
	// SO_RCVBUF request is capped at net.core.rmem_max (often only ~208 KiB) and overflow means
	// silently dropped replies, so try SO_RCVBUFFORCE (root only, bypasses the cap) first.
	if err := syscall.SetsockoptInt(fd, syscall.SOL_SOCKET, soRcvbufForce, 8*1024*1024); err != nil {
		_ = syscall.SetsockoptInt(fd, syscall.SOL_SOCKET, syscall.SO_RCVBUF, 8*1024*1024)
	}
	if got, err := syscall.GetsockoptInt(fd, syscall.SOL_SOCKET, syscall.SO_RCVBUF); err == nil {
		// The kernel reports twice the requested size (it counts its own bookkeeping overhead).
		p.notes = append(p.notes, fmt.Sprintf("receive queue: %d KiB", got/1024))
	}
	// Ask the kernel to timestamp every received packet in software.
	if err := syscall.SetsockoptInt(fd, syscall.SOL_SOCKET, soTimestamping, sofRxSoftware|sofSoftware); err == nil {
		p.clock = "SO_TIMESTAMPING software"
	} else if err := syscall.SetsockoptInt(fd, syscall.SOL_SOCKET, soTimestampNS, 1); err == nil {
		p.clock = "SO_TIMESTAMPNS (software)"
	} else {
		syscall.Close(fd)
		return fmt.Errorf("enabling kernel timestamps: %w", err)
	}
	p.fd = fd
	p.file = os.NewFile(uintptr(fd), "icmp-raw") // pollable because the fd is non-blocking
	rc, err := p.file.SyscallConn()
	if err != nil {
		return err
	}
	p.rc = rc
	p.pending = make(map[uint32]*pending)
	p.expired = make(map[uint32]*pending)
	return nil
}

// readLoop is the reader goroutine, the counterpart of Python's loop.add_reader
// callback. rc.Read parks this goroutine in the netpoller until the socket is
// readable, then runs the closure; returning false means "no more data now,
// wait again".
func (p *prober) readLoop() {
	buf := make([]byte, 1500) // preallocated packet buffer, reused for every packet
	oob := make([]byte, 1024) // ancillary-data (cmsg) buffer
	_ = p.rc.Read(func(fd uintptr) bool {
		var drained []*pending
		for {
			// recvmsg returns the packet bytes in buf AND the control messages in oob.
			n, oobn, _, _, err := syscall.Recvmsg(int(fd), buf, oob, 0)
			if err != nil {
				if err == syscall.EINTR {
					continue
				}
				break // EAGAIN: queue empty (or a fatal error): stop draining
			}
			// ---- Clock B: first thing after the syscall returns ----
			userReal := time.Now().UnixNano() // wall clock = CLOCK_REALTIME, same domain as Clock A

			// ---- Clock A: unpack the kernel timestamp from the cmsg ----
			// ParseSocketControlMessage walks the raw oob bytes ({len, level, type} headers
			// followed by data) and returns them as a slice. For SCM_TIMESTAMPING the data
			// is struct scm_timestamping = 3 x struct timespec, each {int64 sec; int64 nsec}
			// (16 bytes), little-endian on x86_64:
			//     ts[0] software stamp   ts[1] legacy (unused)   ts[2] raw NIC hardware stamp
			// Python reads the same bytes with struct.unpack("=6q"); Rust casts them to [timespec;3].
			var krx int64
			var hasK bool
			if msgs, perr := syscall.ParseSocketControlMessage(oob[:oobn]); perr == nil {
				for _, m := range msgs {
					if m.Header.Level != syscall.SOL_SOCKET {
						continue
					}
					if m.Header.Type == scmTimestamping && len(m.Data) >= 48 {
						sec := int64(binary.LittleEndian.Uint64(m.Data[0:8]))
						nsec := int64(binary.LittleEndian.Uint64(m.Data[8:16]))
						if sec != 0 || nsec != 0 {
							krx, hasK = sec*1_000_000_000+nsec, true
						}
					} else if m.Header.Type == scmTimestampNS && len(m.Data) >= 16 {
						sec := int64(binary.LittleEndian.Uint64(m.Data[0:8]))
						nsec := int64(binary.LittleEndian.Uint64(m.Data[8:16]))
						krx, hasK = sec*1_000_000_000+nsec, true
					}
				}
			}

			// A raw socket hands us the IP header too: low nibble of byte 0 = length in 32-bit words.
			if n < 20 {
				continue
			}
			ihl := int(buf[0]&0x0f) * 4
			if n < ihl+8 || buf[ihl] != icmpEchoReply {
				continue
			}
			id := binary.BigEndian.Uint16(buf[ihl+4:])
			seq := binary.BigEndian.Uint16(buf[ihl+6:])
			key := uint32(id)<<16 | uint32(seq)

			p.mu.Lock()
			pd := p.pending[key]
			delete(p.pending, key)
			var lateOne *pending
			if pd == nil {
				lateOne = p.expired[key]
				delete(p.expired, key)
			}
			p.mu.Unlock()
			if pd == nil {
				if lateOne == nil {
					p.unmatched.Add(1) // somebody else's ping (or a duplicate reply)
				} else { // our ping, but it had already timed out: report it the moment it arrives
					p.late.Add(1)
					var k any
					if hasK {
						k = krx
					}
					p.emit(map[string]any{"e": "late", "icmp_id": lateOne.id, "seq": lateOne.seq,
						"tx": lateOne.tx, "krx": k, "urx": userReal})
				}
				continue
			}
			pd.krx, pd.hasK, pd.urx = krx, hasK, userReal
			drained = append(drained, pd)
		}
		if len(drained) > 0 {
			w := p.wakeups.Add(1)
			p.replied.Add(int64(len(drained)))
			for _, pd := range drained {
				pd.batch, pd.wakeup, pd.got = len(drained), w, true // queue depth seen by this wakeup
				close(pd.done)
			}
		}
		return false
	})
}

// ping sends one echo request and waits for its reply or the timeout. The send time (tx) is read
// just before sendto(), so the kernel RTT includes this host's own send path.
func (p *prober) ping(addr [4]byte, id, seq uint16, timeout time.Duration) *pending {
	pd := &pending{id: id, seq: seq, done: make(chan struct{})}
	key := uint32(id)<<16 | uint32(seq)
	p.mu.Lock()
	p.pending[key] = pd // register BEFORE sending so a fast reply cannot beat us
	p.mu.Unlock()
	pkt := buildEchoRequest(id, seq)
	pd.tx = time.Now().UnixNano()
	if err := syscall.Sendto(p.fd, pkt, 0, &syscall.SockaddrInet4{Addr: addr}); err != nil {
		p.mu.Lock()
		delete(p.pending, key)
		p.mu.Unlock()
		return pd
	}
	p.sent.Add(1)
	select {
	case <-pd.done:
	case <-time.After(timeout):
		p.mu.Lock()
		_, stillThere := p.pending[key]
		delete(p.pending, key)
		if stillThere {
			p.expired[key] = pd // remember it: a late reply may still come
		}
		p.mu.Unlock()
		if !stillThere {
			<-pd.done // the reader just claimed it; wait for it to finish filling the struct
		}
	}
	return pd
}

// ---------------------------------------------------------------------------
// JSON-line events (same schema as probe_lab.py --jsonl)
// ---------------------------------------------------------------------------
func (p *prober) emit(v any) {
	t0 := time.Now()
	b, _ := json.Marshal(v)
	p.emitMu.Lock()
	_, err := os.Stdout.Write(append(b, '\n'))
	p.emitMu.Unlock()
	if err != nil {
		// The reader (the dashboard) is gone: nobody is left to measure for. Go never changes the NIC,
		// and the kernel closes the socket when the process ends, so stopping right away is clean.
		fmt.Fprintln(os.Stderr, "probe: output closed (the dashboard is gone): stopping")
		os.Exit(3)
	}
	p.emitNs.Add(int64(time.Since(t0)))
	p.emitN.Add(1)
}

// ---------------------------------------------------------------------------
// Simulated ORM work
// ---------------------------------------------------------------------------
// burn is a CPU spin that never blocks. In Python it freezes the whole event
// loop; in Go it occupies one P (scheduler slot) of GOMAXPROCS.
func burn(d time.Duration) {
	end := time.Now().Add(d)
	for time.Now().Before(end) {
	}
}

// ---------------------------------------------------------------------------
// Config / helpers
// ---------------------------------------------------------------------------
type route struct {
	Target string `json:"target"`
	Iface  string `json:"interface"`
	SrcIP  string `json:"src_ip"`
}

// discoverRoute: connect() on a UDP socket sends nothing but makes the kernel pick
// the outgoing interface address; map that address back to an interface name.
func discoverRoute(target string) route {
	r := route{target, "?", "?"}
	c, err := net.Dial("udp", net.JoinHostPort(target, "9"))
	if err != nil {
		return r
	}
	defer c.Close()
	src := c.LocalAddr().(*net.UDPAddr).IP
	r.SrcIP = src.String()
	ifs, _ := net.Interfaces()
	for _, ifc := range ifs {
		addrs, _ := ifc.Addrs()
		for _, a := range addrs {
			if ipn, ok := a.(*net.IPNet); ok && ipn.IP.Equal(src) {
				r.Iface = ifc.Name
				return r
			}
		}
	}
	return r
}

// parseIPv4 accepts a dotted IPv4 address only.
func parseIPv4(s string) ([4]byte, error) {
	var out [4]byte
	ip := net.ParseIP(strings.TrimSpace(s)).To4()
	if ip == nil {
		return out, fmt.Errorf("bad IPv4 %q", s)
	}
	copy(out[:], ip)
	return out, nil
}

// fatal prints msg to stderr and exits with status 1.
func fatal(msg string) {
	fmt.Fprintln(os.Stderr, msg)
	os.Exit(1)
}

// maybePin re-executes this program under `taskset -c N` once. sched_setaffinity
// applies per OS thread and the Go runtime has already started several by the time
// main() runs, so pinning from inside would miss them; taskset sets the mask before
// the runtime starts, so every thread inherits it.
func maybePin(cpu int) {
	if cpu < 0 || os.Getenv("GO_PROBER_PINNED") == "1" {
		return
	}
	ts, err := exec.LookPath("taskset")
	if err != nil {
		fmt.Fprintln(os.Stderr, "warning: taskset not found; running unpinned")
		return
	}
	self, _ := os.Executable()
	args := append([]string{"taskset", "-c", strconv.Itoa(cpu), self}, os.Args[1:]...)
	_ = syscall.Exec(ts, args, append(os.Environ(), "GO_PROBER_PINNED=1"))
	fmt.Fprintln(os.Stderr, "warning: could not exec taskset; running unpinned")
}

// main parses the options (the same names as probe_lab.py), applies the CPU mode, and runs every
// endpoint as its own goroutine, writing NDJSON events to stdout for the dashboard.
func main() {
	targets := flag.String("targets", "", "comma-separated IPv4 targets")
	endpoints := flag.Int("virtual-endpoints", 1, "virtual endpoints")
	pings := flag.Int("pings", 5, "pings per cycle")
	interval := flag.Float64("interval", 1.0, "seconds between pings of one endpoint")
	timeout := flag.Float64("timeout", 2.0, "reply timeout (s)")
	cycles := flag.Int("cycles", 1, "cycles per endpoint")
	cycleLen := flag.Float64("cycle-length", 60, "seconds from one cycle's start to the next (when --cycles > 1)")
	stagger := flag.Float64("stagger-window", 0, "seconds over which endpoint starts are spread (0 = burst)")
	semN := flag.Int("semaphore", 15, "db_write_semaphore")
	dbMs := flag.Float64("simulated-db-ms", 3.0, "CPU-bound ORM work per endpoint cycle")
	dbIoMs := flag.Float64("simulated-db-io-ms", 1.0, "async I/O sleep inside the DB write")
	idBase := flag.Int("id-base", 0x1000, "first icmp_id")
	cpuMode := flag.String("cpu-mode", "single_core", "single_core (GOMAXPROCS=1) | multi_core")
	cpu := flag.Int("cpu", -1, "core to pin to in single_core mode (-1 = do not pin)")
	noWarm := flag.Bool("no-warmup", false, "skip the ARP-priming ping")
	_ = flag.Bool("jsonl", true, "accepted for CLI parity; this worker always speaks NDJSON")
	flag.Parse()

	if *cpuMode == "single_core" {
		maybePin(*cpu)
		runtime.GOMAXPROCS(1)
	}
	// Catch Ctrl-C / the dashboard's Stop from the very start (after the taskset re-exec,
	// which replaces this process). Registered later, a stop during socket setup or the
	// warm-up ping would kill the process with no summary event.
	// Notify is called here, not inside the goroutine, so the handler is in place before
	// main continues (a goroutine might not have run yet when an early signal arrives).
	// A broken stdout pipe must come back as an error from Write (handled in emit), not as SIGPIPE
	// killing the process mid-way.
	signal.Ignore(syscall.SIGPIPE)
	stop := make(chan struct{})
	var stopped atomic.Bool
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	go func() {
		<-sig
		stopped.Store(true)
		close(stop)
	}()
	var addrs [][4]byte
	var tstr []string
	for _, t := range strings.Split(*targets, ",") {
		if strings.TrimSpace(t) == "" {
			continue
		}
		a, err := parseIPv4(t)
		if err != nil {
			fatal(err.Error())
		}
		addrs, tstr = append(addrs, a), append(tstr, strings.TrimSpace(t))
	}
	if len(addrs) == 0 {
		fatal("--targets required")
	}
	// icmp_id is 16 bits: endpoints use id-base .. id-base+N-1 and the warm-up pings the next
	// len(targets) ids. uint16() would silently wrap, giving two endpoints the same id.
	if *cycles < 1 || *cycles**pings > 0x10000 {
		fatal("--cycles x --pings must be between 1 and 65536 (the 16-bit icmp_seq space)")
	}
	if *endpoints < 1 || *idBase < 0 || *idBase+*endpoints+len(addrs) > 0x10000 {
		fatal(fmt.Sprintf("--id-base %d + %d endpoints + %d warm-up ids does not fit the 16-bit icmp_id space",
			*idBase, *endpoints, len(addrs)))
	}

	p := &prober{}
	if err := p.open(); err != nil {
		fatal(err.Error())
	}
	cn := &canary{base: time.Now()}
	go cn.run()
	go p.readLoop()

	var routes []route
	seen := map[string]bool{}
	for _, t := range tstr {
		if !seen[t] {
			seen[t] = true
			routes = append(routes, discoverRoute(t))
		}
	}
	p.emit(map[string]any{"e": "start", "clock": p.clock + " [go GOMAXPROCS=" + strconv.Itoa(runtime.GOMAXPROCS(0)) + "]",
		"notes": p.notes, "routes": routes})

	toDur := func(s float64) time.Duration { return time.Duration(s * float64(time.Second)) }
	if !*noWarm { // prime ARP/neighbour caches so ping #1 isn't an outlier
		var wg sync.WaitGroup
		for i, a := range addrs {
			wg.Add(1)
			go func(i int, a [4]byte) {
				defer wg.Done()
				p.ping(a, uint16(*idBase+*endpoints+i), 0, toDur(*timeout))
			}(i, a)
		}
		warmed := make(chan struct{})
		go func() { wg.Wait(); close(warmed) }()
		select { // a stop during warm-up skips straight to the summary
		case <-warmed:
		case <-stop:
		}
	}

	// Startup is finished: the canary only counts stalls while probes are in flight.
	cn.reset()
	p.sent.Store(0)
	p.replied.Store(0)
	p.wakeups.Store(0)
	p.unmatched.Store(0)
	p.late.Store(0)
	p.mu.Lock()
	p.expired = make(map[uint32]*pending) // warm-up pings are not part of the run
	p.mu.Unlock()

	sem := make(chan struct{}, *semN)

	// heartbeat every 0.5 s
	tickDone := make(chan struct{})
	go func() {
		start := time.Now()
		last := cn.nowNs()
		t := time.NewTicker(500 * time.Millisecond)
		defer t.Stop()
		for {
			select {
			case <-tickDone:
				return
			case <-t.C:
				now := cn.nowNs()
				rec := cn.window(last, now)
				last = now
				cn.mu.Lock()
				mx := cn.maxAll
				cn.mu.Unlock()
				p.emit(map[string]any{"e": "tick", "t": math.Round(time.Since(start).Seconds()*100) / 100,
					"sent": p.sent.Load(), "replied": p.replied.Load(), "reader_calls": p.wakeups.Load(),
					"recent_avg_us": rec.Avg, "recent_max_us": rec.Max, "max_us": r1(mx)})
			}
		}
	}()

	origin := time.Now().Add(100 * time.Millisecond)
	var wg sync.WaitGroup
	for i := 0; i < *endpoints; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			addr := addrs[idx%len(addrs)]
			target := tstr[idx%len(tstr)]
			id := uint16(*idBase + idx)
			var offset float64
			if *stagger > 0 && *endpoints > 1 {
				offset = *stagger * float64(idx) / float64(*endpoints)
			}
			for cyc := 0; cyc < *cycles; cyc++ {
				start := origin.Add(toDur(float64(cyc)**cycleLen + offset))
				select {
				case <-time.After(time.Until(start)):
				case <-stop:
					return
				}
				w0 := cn.nowNs()
				rows := make([][]any, 0, *pings)
				for n := 0; n < *pings; n++ {
					slot := start.Add(time.Duration(n) * toDur(*interval))
					select {
					case <-time.After(time.Until(slot)):
					case <-stop:
						return
					}
					// Send-side observer effect: how late this goroutine got to send vs its slot.
					// time.Since uses the monotonic clock reading carried inside slot.
					sendLag := int64(time.Since(slot))
					seq := uint16(cyc**pings + n) // same numbering as Python: unique across cycles
					pd := p.ping(addr, id, seq, toDur(*timeout))
					if pd.got {
						var k any
						if pd.hasK {
							k = pd.krx
						}
						rows = append(rows, []any{seq, pd.tx, k, pd.urx, nil, pd.batch, pd.wakeup, sendLag})
					} else {
						rows = append(rows, []any{seq, pd.tx, nil, nil, nil, 0, 0, sendLag})
					}
				}
				w1 := cn.nowNs()
				win := cn.window(w0, w1)

				// ---- post-cycle "database write": semaphore -> CPU burn -> async I/O ----
				t0 := time.Now()
				sem <- struct{}{}
				waitMs := float64(time.Since(t0)) / 1e6
				dbStart := time.Now().UnixNano() // CLOCK_REALTIME around the CPU work, for the burst shading
				burn(toDur(*dbMs / 1000))
				dbEnd := time.Now().UnixNano()
				time.Sleep(toDur(*dbIoMs / 1000)) // still holding the semaphore, like Python
				<-sem

				p.emit(map[string]any{"e": "cycle", "ep": idx, "cyc": cyc, "target": target, "icmp_id": id,
					"db_wait_ms": math.Round(waitMs*1000) / 1000, "db_start_ns": dbStart, "db_end_ns": dbEnd,
					"canary": win, "packets": rows})
			}
		}(i)
	}
	finished := make(chan struct{})
	go func() { wg.Wait(); close(finished) }()
	select {
	case <-finished:
	case <-stop:
	}

	// Probing is over: freeze the canary BEFORE any summary work so it cannot pollute the numbers.
	cn.freeze()
	cs := cn.all()
	close(tickDone)
	p.emit(map[string]any{"e": "summary", "sent": p.sent.Load(), "replied": p.replied.Load(),
		"reader_calls": p.wakeups.Load(), "unmatched": p.unmatched.Load(), "late": p.late.Load(), "canary": cs,
		"emit_us_total": r1(float64(p.emitNs.Load()) / 1e3), "emit_n": p.emitN.Load(), "stopped": stopped.Load()})
	cn.stop.Store(true)
	p.file.Close()
}
