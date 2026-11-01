//! rust_prober - the Rust (tokio) engine of the Observer-Effect lab.
//!
//! Replicates probe_lab.py (--jsonl mode) mechanic for mechanic and speaks the
//! same NDJSON protocol on stdout (events: start, cycle, tick, summary), so the
//! dashboard needs no engine-specific code.
//!
//! THE TWO CLOCKS (same as Python and Go)
//!   Clock A  kernel arrival time of the reply, delivered as a control message
//!            (cmsg) alongside the packet by recvmsg().
//!   Clock B  clock_gettime(CLOCK_REALTIME) read the instant recvmsg() returns.
//!   observer lag = B - A = how long the reply waited for this program to read it.
//!
//! HOW RUST/TOKIO DIFFERS FROM PYTHON HERE
//!   single_core -> tokio's *current_thread* runtime: one thread runs every task,
//!                  exactly like asyncio. The inline ORM spin freezes the socket
//!                  reader task, as in Python (but with no interpreter overhead).
//!   NOTE tokio's timers have 1 ms resolution, so this engine's idle canary reads about 1 ms of lag
//!   (Python and Go idle at roughly 0.1-0.4 ms). Compare canary *increases* between engines.
//!   multi_core  -> tokio's multi-thread runtime: the reader task can run on
//!                  another worker thread while one worker is busy spinning.
//!
//! Build: see ../../build_workers.sh

use std::collections::HashMap;
use std::io::Write;
use std::mem;
use std::net::{Ipv4Addr, UdpSocket};
use std::os::unix::io::{AsRawFd, RawFd};
use std::sync::atomic::{AtomicBool, AtomicI64, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use tokio::io::unix::AsyncFd;
use tokio::sync::{oneshot, Semaphore};

// Linux constants (values from the kernel UAPI headers; not all are exported by libc).
const SO_TIMESTAMPING: libc::c_int = 37; // setsockopt option
const SO_TIMESTAMPNS: libc::c_int = 35; // older, simpler option
const SCM_TIMESTAMPING: libc::c_int = 37; // cmsg type: struct scm_timestamping (3 x timespec)
const SCM_TIMESTAMPNS: libc::c_int = 35; // cmsg type: one timespec
const SO_RCVBUFFORCE: libc::c_int = 33; // set the receive queue size ignoring net.core.rmem_max (root)
const SOL_RAW: libc::c_int = 255;
const ICMP_FILTER: libc::c_int = 1; // struct icmp_filter { u32 data }: bit N set => BLOCK type N
const SOF_RX_SOFTWARE: libc::c_int = 1 << 3;
const SOF_SOFTWARE: libc::c_int = 1 << 4;
const ICMP_ECHO_REPLY: u8 = 0;
const PAYLOAD_LEN: usize = 56;
const CANARY_TICK: Duration = Duration::from_millis(10);
const CANARY_MAX_SAMPLES: usize = 120_000;

// ---------------------------------------------------------------------------
// Clocks
// ---------------------------------------------------------------------------
/// CLOCK_REALTIME in ns: the same clock domain the kernel uses for its packet stamps.
fn now_real_ns() -> i64 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    unsafe { libc::clock_gettime(libc::CLOCK_REALTIME, &mut ts) };
    ts.tv_sec as i64 * 1_000_000_000 + ts.tv_nsec as i64
}

// ---------------------------------------------------------------------------
// ICMP packet building (identical bytes to the Python and Go engines)
// ---------------------------------------------------------------------------
/// RFC 1071 Internet checksum. A raw ICMP socket adds the IP header but not this.
fn icmp_checksum(b: &[u8]) -> u16 {
    let mut sum: u32 = 0;
    let mut i = 0;
    while i + 1 < b.len() {
        sum += u16::from_be_bytes([b[i], b[i + 1]]) as u32;
        i += 2;
    }
    if b.len() % 2 == 1 {
        sum += (b[b.len() - 1] as u32) << 8;
    }
    while sum >> 16 != 0 {
        sum = (sum & 0xffff) + (sum >> 16);
    }
    !(sum as u16)
}

/// type 8, code 0, checksum, id, seq + 56 payload bytes. RFC 792 forces every
/// responder to echo id+seq back: that is the return address for each endpoint.
fn build_echo_request(id: u16, seq: u16) -> Vec<u8> {
    let mut pkt = vec![0u8; 8 + PAYLOAD_LEN];
    pkt[0] = 8;
    pkt[4..6].copy_from_slice(&id.to_be_bytes());
    pkt[6..8].copy_from_slice(&seq.to_be_bytes());
    pkt[8..16].copy_from_slice(b"EPHEMRES");
    pkt[16..18].copy_from_slice(&id.to_be_bytes());
    pkt[18..20].copy_from_slice(&seq.to_be_bytes());
    for b in pkt[20..].iter_mut() {
        *b = 0xa5;
    }
    let c = icmp_checksum(&pkt);
    pkt[2..4].copy_from_slice(&c.to_be_bytes());
    pkt
}

// ---------------------------------------------------------------------------
// Raw socket
// ---------------------------------------------------------------------------
struct Fd(RawFd);
impl AsRawFd for Fd {
    fn as_raw_fd(&self) -> RawFd {
        self.0
    }
}
impl Drop for Fd {
    fn drop(&mut self) {
        unsafe { libc::close(self.0) };
    }
}

/// Set an integer socket option; returns false if the kernel refused it.
fn setsockopt_int(fd: RawFd, level: libc::c_int, opt: libc::c_int, val: libc::c_int) -> bool {
    unsafe {
        libc::setsockopt(fd, level, opt, &val as *const _ as *const libc::c_void, mem::size_of::<libc::c_int>() as u32) == 0
    }
}

/// Opens the shared raw ICMP socket. Returns (fd, description of the Clock-A mode).
fn open_socket() -> Result<(Fd, String, String), String> {
    // SOCK_NONBLOCK so tokio's epoll reactor (AsyncFd) can wait on it without blocking a thread.
    let fd = unsafe { libc::socket(libc::AF_INET, libc::SOCK_RAW | libc::SOCK_NONBLOCK | libc::SOCK_CLOEXEC, libc::IPPROTO_ICMP) };
    if fd < 0 {
        return Err(format!("raw ICMP socket: {} (need root or cap_net_raw)", std::io::Error::last_os_error()));
    }
    let fd = Fd(fd);
    // Deliver only Echo Replies (bit N set => block ICMP type N).
    setsockopt_int(fd.0, SOL_RAW, ICMP_FILTER, !(1u32 << ICMP_ECHO_REPLY) as libc::c_int);
    // Big receive queue: while this program is busy, replies pile up in the kernel. A plain
    // SO_RCVBUF request is capped at net.core.rmem_max (often only ~208 KiB) and overflow means
    // silently dropped replies, so try SO_RCVBUFFORCE (root only, bypasses the cap) first.
    if !setsockopt_int(fd.0, libc::SOL_SOCKET, SO_RCVBUFFORCE, 8 * 1024 * 1024) {
        setsockopt_int(fd.0, libc::SOL_SOCKET, libc::SO_RCVBUF, 8 * 1024 * 1024);
    }
    let mut got: libc::c_int = 0;
    let mut len = mem::size_of::<libc::c_int>() as u32;
    unsafe { libc::getsockopt(fd.0, libc::SOL_SOCKET, libc::SO_RCVBUF, &mut got as *mut _ as *mut libc::c_void, &mut len) };
    // The kernel reports twice the requested size (it counts its own bookkeeping overhead).
    let rcvbuf_note = format!("receive queue: {} KiB", got / 1024);
    // Ask the kernel to timestamp every received packet in software.
    let mode = if setsockopt_int(fd.0, libc::SOL_SOCKET, SO_TIMESTAMPING, SOF_RX_SOFTWARE | SOF_SOFTWARE) {
        "SO_TIMESTAMPING software"
    } else if setsockopt_int(fd.0, libc::SOL_SOCKET, SO_TIMESTAMPNS, 1) {
        "SO_TIMESTAMPNS (software)"
    } else {
        return Err(format!("enabling kernel timestamps: {}", std::io::Error::last_os_error()));
    };
    Ok((fd, mode.to_string(), rcvbuf_note))
}

/// One packet read from the socket, with both clocks.
struct Reception {
    id: u16,
    seq: u16,
    krx: Option<i64>, // Clock A (kernel arrival, CLOCK_REALTIME ns)
    urx: i64,         // Clock B (user space, CLOCK_REALTIME ns)
}

/// Non-blocking recvmsg: packet bytes land in `buf`, control messages in `oob`.
fn recv_one(fd: RawFd, buf: &mut [u8], oob: &mut [u8]) -> std::io::Result<Option<Reception>> {
    // recvmsg takes a `struct msghdr` describing two output buffers:
    //   msg_iov     -> where the packet bytes go (our preallocated 1500-byte buffer)
    //   msg_control -> where ancillary data ("cmsg") goes (kernel timestamps)
    let mut iov = libc::iovec { iov_base: buf.as_mut_ptr() as *mut libc::c_void, iov_len: buf.len() };
    let mut msg: libc::msghdr = unsafe { mem::zeroed() };
    msg.msg_iov = &mut iov;
    msg.msg_iovlen = 1;
    msg.msg_control = oob.as_mut_ptr() as *mut libc::c_void;
    msg.msg_controllen = oob.len() as _;
    let n = unsafe { libc::recvmsg(fd, &mut msg, 0) };
    if n < 0 {
        return Err(std::io::Error::last_os_error()); // WouldBlock = queue empty
    }
    // ---- Clock B: first thing after the syscall returns ----
    let urx = now_real_ns();

    // ---- Clock A: walk the cmsg list ----
    // Each control message is {cmsg_len, cmsg_level, cmsg_type} followed by its data.
    // For SCM_TIMESTAMPING the data is `struct scm_timestamping` = [timespec; 3]
    // (each {i64 sec, i64 nsec}): ts[0] software, ts[1] legacy/unused, ts[2] raw NIC hardware.
    // Here we reinterpret those raw bytes as a Rust array of libc::timespec; Python
    // uses struct.unpack("=6q") and Go reads the integers with encoding/binary.
    let mut krx: Option<i64> = None;
    unsafe {
        let mut c = libc::CMSG_FIRSTHDR(&msg);
        while !c.is_null() {
            if (*c).cmsg_level == libc::SOL_SOCKET {
                let data = libc::CMSG_DATA(c);
                // Only read as many bytes as the kernel says the payload holds (Python and Go
                // check the same thing): cmsg_len counts the header plus the data.
                let data_len = ((*c).cmsg_len as usize).saturating_sub(libc::CMSG_LEN(0) as usize);
                if (*c).cmsg_type == SCM_TIMESTAMPING && data_len >= mem::size_of::<[libc::timespec; 3]>() {
                    let ts: [libc::timespec; 3] = std::ptr::read_unaligned(data as *const [libc::timespec; 3]);
                    if ts[0].tv_sec != 0 || ts[0].tv_nsec != 0 {
                        krx = Some(ts[0].tv_sec as i64 * 1_000_000_000 + ts[0].tv_nsec as i64);
                    }
                } else if (*c).cmsg_type == SCM_TIMESTAMPNS && data_len >= mem::size_of::<libc::timespec>() {
                    let ts: libc::timespec = std::ptr::read_unaligned(data as *const libc::timespec);
                    krx = Some(ts.tv_sec as i64 * 1_000_000_000 + ts.tv_nsec as i64);
                }
            }
            c = libc::CMSG_NXTHDR(&msg, c);
        }
    }

    // The raw socket also hands us the IP header: low nibble of byte 0 = length in 32-bit words.
    let n = n as usize;
    if n < 20 {
        return Ok(None);
    }
    let ihl = ((buf[0] & 0x0f) as usize) * 4;
    if n < ihl + 8 || buf[ihl] != ICMP_ECHO_REPLY {
        return Ok(None);
    }
    let id = u16::from_be_bytes([buf[ihl + 4], buf[ihl + 5]]);
    let seq = u16::from_be_bytes([buf[ihl + 6], buf[ihl + 7]]);
    Ok(Some(Reception { id, seq, krx, urx }))
}

// ---------------------------------------------------------------------------
// Shared state
// ---------------------------------------------------------------------------
struct RxInfo {
    krx: Option<i64>,
    urx: i64,
    batch: u32,
    wakeup: u64,
}

/// A task that sleeps 10 ms in a loop and records how late each wake-up was. Lateness means the
/// runtime had no free thread for it: the same delay the socket reader suffers.
struct Canary {
    base: Instant,
    samples: Mutex<Vec<(i64, i64, f64)>>, // (start_ns, end_ns, lag_us), monotonic since base
    epoch: AtomicI64,                     // ticks that began before this are ignored (startup)
    frozen: AtomicBool,                   // closed gate: teardown / summary work is not measured
    max_all: Mutex<f64>,
}

impl Canary {
    fn now_ns(&self) -> i64 {
        self.base.elapsed().as_nanos() as i64
    }
    /// Opens the measurement gate (call once startup/warm-up is finished).
    fn reset(&self) {
        let mut s = self.samples.lock().unwrap();
        s.clear();
        *self.max_all.lock().unwrap() = 0.0;
        self.epoch.store(self.now_ns(), Ordering::SeqCst);
        self.frozen.store(false, Ordering::SeqCst);
    }
    /// Closes the gate (call before teardown and summary formatting).
    fn freeze(&self) {
        self.frozen.store(true, Ordering::SeqCst);
    }
    async fn run(self: Arc<Self>) {
        let tick_ns = CANARY_TICK.as_nanos() as i64;
        loop {
            let t0 = self.now_ns();
            tokio::time::sleep(CANARY_TICK).await;
            let t1 = self.now_ns();
            if self.frozen.load(Ordering::SeqCst) || t0 < self.epoch.load(Ordering::SeqCst) {
                continue;
            }
            let lag = ((t1 - t0 - tick_ns) as f64 / 1000.0).max(0.0);
            let mut s = self.samples.lock().unwrap();
            s.push((t0, t1, lag));
            if s.len() > CANARY_MAX_SAMPLES {
                s.drain(0..CANARY_MAX_SAMPLES / 2);
            }
            let mut m = self.max_all.lock().unwrap();
            if lag > *m {
                *m = lag;
            }
        }
    }
    /// Stats of ticks overlapping [start,end]; walks newest-first and stops early.
    fn window(&self, start: i64, end: i64) -> Value {
        let s = self.samples.lock().unwrap();
        let mut lags = Vec::new();
        for &(a, b, lag) in s.iter().rev() {
            if b < start {
                break;
            }
            if a <= end {
                lags.push(lag);
            }
        }
        summarise(lags)
    }
    fn all(&self) -> Value {
        let s = self.samples.lock().unwrap();
        summarise(s.iter().map(|x| x.2).collect())
    }
}

/// Round to one decimal, for compact JSON.
fn r1(x: f64) -> f64 {
    (x * 10.0).round() / 10.0
}

/// Average, p95 and max of canary lateness samples (µs), with the same field names in all engines.
fn summarise(mut lags: Vec<f64>) -> Value {
    if lags.is_empty() {
        return json!({"avg_lag_us": 0.0, "p95_lag_us": 0.0, "max_lag_us": 0.0, "samples": 0});
    }
    lags.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let sum: f64 = lags.iter().sum();
    let pos = (lags.len() - 1) as f64 * 0.95; // linear-interpolated percentile (numpy default)
    let lo = pos as usize;
    let hi = (lo + 1).min(lags.len() - 1);
    let p95 = lags[lo] + (lags[hi] - lags[lo]) * (pos - lo as f64);
    json!({"avg_lag_us": r1(sum / lags.len() as f64), "p95_lag_us": r1(p95),
           "max_lag_us": r1(*lags.last().unwrap()), "samples": lags.len()})
}

/// State shared by all endpoint tasks and the reader: the socket, the pings waiting for a reply
/// (keyed by icmp_id << 16 | icmp_seq) and the run's counters.
struct Shared {
    fd: RawFd,
    pending: Mutex<HashMap<u32, oneshot::Sender<RxInfo>>>,
    // Pings that timed out: (icmp_id, seq, tx_ns). A reply that turns up later is reported as LATE
    // with its kernel stamp; if that stamp is inside the timeout, the "loss" was this program's fault.
    expired: Mutex<HashMap<u32, (u16, u16, i64)>>,
    late: AtomicU64,
    sent: AtomicU64,
    replied: AtomicU64,
    wakeups: AtomicU64,
    unmatched: AtomicU64,
    emit_ns: AtomicU64,
    emit_n: AtomicU64,
    out: Mutex<()>,
    canary: Arc<Canary>,
}

impl Shared {
    /// One JSON line on stdout, timed so the dashboard can report the streaming overhead.
    fn emit(&self, v: Value) {
        let t0 = Instant::now();
        let line = v.to_string();
        {
            let _g = self.out.lock().unwrap();
            let mut so = std::io::stdout().lock();
            if writeln!(so, "{}", line).and_then(|_| so.flush()).is_err() {
                // The reader (the dashboard) is gone: nobody is left to measure for. Rust never changes the
                // NIC and the kernel closes the socket at exit, so stopping right away is clean.
                eprintln!("probe: output closed (the dashboard is gone): stopping");
                std::process::exit(3);
            }
        }
        self.emit_ns.fetch_add(t0.elapsed().as_nanos() as u64, Ordering::Relaxed);
        self.emit_n.fetch_add(1, Ordering::Relaxed);
    }
}

/// The reader task: the counterpart of Python's loop.add_reader callback.
/// AsyncFd registers the fd with tokio's epoll; `readable().await` parks this task
/// until the kernel says there is data, then we drain until EAGAIN.
async fn reader(afd: AsyncFd<Fd>, sh: Arc<Shared>) {
    let mut buf = vec![0u8; 1500]; // preallocated packet buffer, reused for every packet
    let mut oob = vec![0u8; 1024]; // ancillary-data (cmsg) buffer
    loop {
        let mut guard = match afd.readable().await {
            Ok(g) => g,
            Err(_) => return,
        };
        let mut drained: Vec<(oneshot::Sender<RxInfo>, Option<i64>, i64)> = Vec::new();
        loop {
            match recv_one(afd.get_ref().0, &mut buf, &mut oob) {
                Ok(Some(rx)) => {
                    let key = (rx.id as u32) << 16 | rx.seq as u32;
                    let tx = sh.pending.lock().unwrap().remove(&key);
                    match tx {
                        Some(tx) => drained.push((tx, rx.krx, rx.urx)),
                        None => match sh.expired.lock().unwrap().remove(&key) {
                            // our ping, but it had already timed out: report it the moment it arrives
                            Some((id, seq, tx_ns)) => {
                                sh.late.fetch_add(1, Ordering::Relaxed);
                                sh.emit(json!({"e": "late", "icmp_id": id, "seq": seq, "tx": tx_ns,
                                               "krx": rx.krx, "urx": rx.urx}));
                            }
                            None => {
                                sh.unmatched.fetch_add(1, Ordering::Relaxed); // someone else's ping
                            }
                        },
                    }
                }
                Ok(None) => continue,
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(_) => break, // WouldBlock: queue empty
            }
        }
        guard.clear_ready(); // tell tokio we drained to EAGAIN so it re-arms epoll
        if !drained.is_empty() {
            let w = sh.wakeups.fetch_add(1, Ordering::Relaxed) + 1;
            sh.replied.fetch_add(drained.len() as u64, Ordering::Relaxed);
            let batch = drained.len() as u32; // queue depth seen by this wakeup
            for (tx, krx, urx) in drained {
                let _ = tx.send(RxInfo { krx, urx, batch, wakeup: w });
            }
        }
    }
}

/// One ping's outcome: its send time and, if it came back in time, the reply's stamps.
struct PingResult {
    tx_ns: i64,
    rx: Option<RxInfo>,
}

/// Send one echo request and wait for its reply or the timeout. The send time is read just before
/// sendto(), so the kernel RTT includes this host's own send path.
async fn ping(sh: &Arc<Shared>, dst: Ipv4Addr, id: u16, seq: u16, timeout: Duration) -> PingResult {
    let (tx, mut rx) = oneshot::channel();
    let key = (id as u32) << 16 | seq as u32;
    sh.pending.lock().unwrap().insert(key, tx); // register BEFORE sending so a fast reply cannot beat us
    let pkt = build_echo_request(id, seq);
    let addr = libc::sockaddr_in {
        sin_family: libc::AF_INET as libc::sa_family_t,
        sin_port: 0,
        sin_addr: libc::in_addr { s_addr: u32::from_ne_bytes(dst.octets()) }, // already network order
        sin_zero: [0; 8],
    };
    let tx_ns = now_real_ns();
    let r = unsafe {
        libc::sendto(sh.fd, pkt.as_ptr() as *const libc::c_void, pkt.len(), 0,
                     &addr as *const _ as *const libc::sockaddr, mem::size_of::<libc::sockaddr_in>() as u32)
    };
    if r < 0 {
        sh.pending.lock().unwrap().remove(&key);
        return PingResult { tx_ns, rx: None };
    }
    sh.sent.fetch_add(1, Ordering::Relaxed);
    match tokio::time::timeout(timeout, &mut rx).await {
        Ok(Ok(info)) => PingResult { tx_ns, rx: Some(info) },
        Ok(Err(_)) => PingResult { tx_ns, rx: None }, // sender dropped without a reply
        Err(_) => {
            // Timed out.  If our entry is gone, the reader already claimed this reply (it was
            // counted in `replied`) and is about to send it: wait for it rather than drop it,
            // or the row would say "lost" while the counters say "replied" (Go does the same).
            let still_pending = sh.pending.lock().unwrap().remove(&key).is_some();
            if still_pending {
                sh.expired.lock().unwrap().insert(key, (id, seq, tx_ns)); // a late reply may still come
                PingResult { tx_ns, rx: None }
            } else {
                PingResult { tx_ns, rx: rx.await.ok() }
            }
        }
    }
}

/// CPU spin that never yields. In Python it freezes the event loop; with tokio it
/// occupies one runtime worker thread (the only one in single_core mode).
fn burn(d: Duration) {
    let end = Instant::now() + d;
    while Instant::now() < end {}
}

// ---------------------------------------------------------------------------
// Config / CLI
// ---------------------------------------------------------------------------
struct Cfg {
    targets: Vec<Ipv4Addr>,
    endpoints: usize,
    pings: usize,
    interval: f64,
    timeout: f64,
    cycles: usize,
    cycle_len: f64,
    stagger: f64,
    semaphore: usize,
    db_ms: f64,
    db_io_ms: f64,
    id_base: u32,
    single_core: bool,
    cpu: i32,
    warmup: bool,
}

/// Parse the command line; option names are the same as probe_lab.py's.
fn parse_args() -> Result<Cfg, String> {
    let mut c = Cfg { targets: vec![], endpoints: 1, pings: 5, interval: 1.0, timeout: 2.0, cycles: 1, cycle_len: 60.0, stagger: 0.0, semaphore: 15,
                      db_ms: 3.0, db_io_ms: 1.0, id_base: 0x1000, single_core: true, cpu: -1, warmup: true };
    let a: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < a.len() {
        let key = a[i].as_str();
        let mut val = || -> Result<String, String> { i += 1; a.get(i).cloned().ok_or(format!("{} needs a value", key)) };
        match key {
            "--targets" => {
                for t in val()?.split(',').filter(|s| !s.trim().is_empty()) {
                    c.targets.push(t.trim().parse().map_err(|_| format!("bad IPv4 {}", t))?);
                }
            }
            "--virtual-endpoints" => c.endpoints = val()?.parse().map_err(|_| "bad --virtual-endpoints")?,
            "--pings" => c.pings = val()?.parse().map_err(|_| "bad --pings")?,
            "--interval" => c.interval = val()?.parse().map_err(|_| "bad --interval")?,
            "--timeout" => c.timeout = val()?.parse().map_err(|_| "bad --timeout")?,
            "--stagger-window" => c.stagger = val()?.parse().map_err(|_| "bad --stagger-window")?,
            "--cycles" => c.cycles = val()?.parse().map_err(|_| "bad --cycles")?,
            "--cycle-length" => c.cycle_len = val()?.parse().map_err(|_| "bad --cycle-length")?,
            "--semaphore" => c.semaphore = val()?.parse().map_err(|_| "bad --semaphore")?,
            "--simulated-db-ms" => c.db_ms = val()?.parse().map_err(|_| "bad --simulated-db-ms")?,
            "--simulated-db-io-ms" => c.db_io_ms = val()?.parse().map_err(|_| "bad --simulated-db-io-ms")?,
            "--id-base" => c.id_base = val()?.parse().map_err(|_| "bad --id-base")?,
            "--cpu-mode" => c.single_core = val()? != "multi_core",
            "--cpu" => c.cpu = val()?.parse().map_err(|_| "bad --cpu")?,
            "--no-warmup" => c.warmup = false,
            "--jsonl" => {} // accepted for CLI parity; this worker always speaks NDJSON
            other => return Err(format!("unknown flag {}", other)),
        }
        i += 1;
    }
    if c.targets.is_empty() {
        return Err("--targets required".into());
    }
    // icmp_id is 16 bits: endpoints use id-base .. id-base+N-1 and the warm-up pings the next
    // targets.len() ids. `as u16` would silently wrap, giving two endpoints the same id.
    if c.cycles == 0 || c.cycles * c.pings > 0x10000 {
        return Err("--cycles x --pings must be between 1 and 65536 (the 16-bit icmp_seq space)".into());
    }
    if c.endpoints == 0 || c.id_base as usize + c.endpoints + c.targets.len() > 0x10000 {
        return Err(format!("--id-base {} + {} endpoints + {} warm-up ids does not fit the 16-bit icmp_id space",
                           c.id_base, c.endpoints, c.targets.len()));
    }
    Ok(c)
}

/// connect() on a UDP socket sends nothing but makes the kernel choose the outgoing
/// source address; getifaddrs() then maps that address back to an interface name.
fn discover_route(target: Ipv4Addr) -> Value {
    let mut src = "?".to_string();
    let mut iface = "?".to_string();
    if let Ok(s) = UdpSocket::bind("0.0.0.0:0") {
        if s.connect((target, 9)).is_ok() {
            if let Ok(la) = s.local_addr() {
                src = la.ip().to_string();
            }
        }
    }
    unsafe {
        let mut ifap: *mut libc::ifaddrs = std::ptr::null_mut();
        if libc::getifaddrs(&mut ifap) == 0 {
            let mut p = ifap;
            while !p.is_null() {
                let a = (*p).ifa_addr;
                if !a.is_null() && (*a).sa_family as i32 == libc::AF_INET {
                    let sin = &*(a as *const libc::sockaddr_in);
                    let ip = Ipv4Addr::from(u32::from_be(sin.sin_addr.s_addr));
                    if ip.to_string() == src {
                        iface = std::ffi::CStr::from_ptr((*p).ifa_name).to_string_lossy().into_owned();
                        break;
                    }
                }
                p = (*p).ifa_next;
            }
            libc::freeifaddrs(ifap);
        }
    }
    json!({"target": target.to_string(), "interface": iface, "src_ip": src})
}

/// Pin the whole process to one core. Called in main() BEFORE the tokio runtime
/// spawns any threads, so every thread inherits the mask.
fn pin_cpu(cpu: i32) {
    if cpu < 0 {
        return;
    }
    unsafe {
        let mut set: libc::cpu_set_t = mem::zeroed();
        libc::CPU_SET(cpu as usize, &mut set);
        if libc::sched_setaffinity(0, mem::size_of::<libc::cpu_set_t>(), &set) != 0 {
            eprintln!("warning: sched_setaffinity({}) failed: {}", cpu, std::io::Error::last_os_error());
        }
    }
}

fn main() {
    let cfg = match parse_args() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("{}", e);
            std::process::exit(2);
        }
    };
    if cfg.single_core {
        pin_cpu(cfg.cpu);
    }
    // single_core: one thread runs every task (like asyncio). multi_core: one worker per CPU.
    let workers = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1);
    let rt = if cfg.single_core {
        tokio::runtime::Builder::new_current_thread().enable_all().build()
    } else {
        tokio::runtime::Builder::new_multi_thread().worker_threads(workers).enable_all().build()
    }
    .expect("tokio runtime");
    let label = if cfg.single_core { "current_thread".to_string() } else { format!("multi_thread x{}", workers) };
    rt.block_on(run(cfg, label));
}

/// The whole run: open the socket, start the reader and the canary, run every endpoint as a task,
/// then print the summary event.
async fn run(cfg: Cfg, label: String) {
    // Catch Ctrl-C / the dashboard's Stop from the very start. Registered later, a stop during
    // socket setup or the warm-up ping would kill the process with no summary event.
    let mut sigint = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::interrupt()).unwrap();
    let mut sigterm = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()).unwrap();
    let mut stopped = false;
    let (fd, mode, rcvbuf_note) = match open_socket() {
        Ok(x) => x,
        Err(e) => {
            eprintln!("{}", e);
            std::process::exit(1);
        }
    };
    let raw = fd.0;
    let canary = Arc::new(Canary { base: Instant::now(), samples: Mutex::new(vec![]), epoch: AtomicI64::new(0),
                                   frozen: AtomicBool::new(false), max_all: Mutex::new(0.0) });
    let sh = Arc::new(Shared { fd: raw, pending: Mutex::new(HashMap::new()), expired: Mutex::new(HashMap::new()),
                               late: AtomicU64::new(0), sent: AtomicU64::new(0),
                               replied: AtomicU64::new(0), wakeups: AtomicU64::new(0), unmatched: AtomicU64::new(0),
                               emit_ns: AtomicU64::new(0), emit_n: AtomicU64::new(0), out: Mutex::new(()),
                               canary: canary.clone() });
    #[allow(deprecated)] // AsyncFd::new is deprecated in newer tokio (I/O-safety); it is still the simplest correct call here
    let afd = AsyncFd::new(fd).expect("AsyncFd");
    tokio::spawn(reader(afd, sh.clone()));
    tokio::spawn(canary.clone().run());

    let mut routes = Vec::new();
    let mut seen = std::collections::HashSet::new();
    for t in &cfg.targets {
        if seen.insert(*t) {
            routes.push(discover_route(*t));
        }
    }
    sh.emit(json!({"e": "start", "clock": format!("{} [rust tokio {}]", mode, label), "notes": [rcvbuf_note], "routes": routes}));

    let dur = |s: f64| Duration::from_secs_f64(s.max(0.0));
    if cfg.warmup {
        // prime ARP/neighbour caches so ping #1 isn't an outlier
        let mut hs = Vec::new();
        for (i, t) in cfg.targets.iter().enumerate() {
            let (sh2, t, id) = (sh.clone(), *t, (cfg.id_base as usize + cfg.endpoints + i) as u16);
            let to = dur(cfg.timeout);
            hs.push(tokio::spawn(async move { ping(&sh2, t, id, 0, to).await }));
        }
        let warm = async {
            for h in hs {
                let _ = h.await;
            }
        };
        tokio::select! { // a stop during warm-up skips straight to the summary
            _ = warm => {}
            _ = sigint.recv() => { stopped = true; }
            _ = sigterm.recv() => { stopped = true; }
        }
    }

    // Startup is finished: the canary only counts stalls while probes are in flight.
    canary.reset();
    for c in [&sh.sent, &sh.replied, &sh.wakeups, &sh.unmatched, &sh.late] {
        c.store(0, Ordering::Relaxed);
    }
    sh.expired.lock().unwrap().clear(); // warm-up pings are not part of the run

    let sem = Arc::new(Semaphore::new(cfg.semaphore));
    let origin = tokio::time::Instant::now() + Duration::from_millis(100);

    // heartbeat every 0.5 s
    let tick_sh = sh.clone();
    let ticker = tokio::spawn(async move {
        let start = Instant::now();
        let mut last = tick_sh.canary.now_ns();
        let mut iv = tokio::time::interval(Duration::from_millis(500));
        iv.tick().await;
        loop {
            iv.tick().await;
            let now = tick_sh.canary.now_ns();
            let rec = tick_sh.canary.window(last, now);
            last = now;
            let mx = *tick_sh.canary.max_all.lock().unwrap();
            tick_sh.emit(json!({"e": "tick", "t": (start.elapsed().as_secs_f64() * 100.0).round() / 100.0,
                "sent": tick_sh.sent.load(Ordering::Relaxed), "replied": tick_sh.replied.load(Ordering::Relaxed),
                "reader_calls": tick_sh.wakeups.load(Ordering::Relaxed),
                "recent_avg_us": rec["avg_lag_us"], "recent_max_us": rec["max_lag_us"], "max_us": r1(mx)}));
        }
    });

    let mut handles = Vec::new();
    for idx in 0..if stopped { 0 } else { cfg.endpoints } {
        let (sh, sem, canary) = (sh.clone(), sem.clone(), canary.clone());
        let target = cfg.targets[idx % cfg.targets.len()];
        let (pings, interval, timeout) = (cfg.pings, cfg.interval, cfg.timeout);
        let (cycles, cycle_len) = (cfg.cycles, cfg.cycle_len);
        let (db_ms, db_io_ms) = (cfg.db_ms, cfg.db_io_ms);
        let id = (cfg.id_base as usize + idx) as u16;
        let offset = if cfg.stagger > 0.0 && cfg.endpoints > 1 { cfg.stagger * idx as f64 / cfg.endpoints as f64 } else { 0.0 };
        handles.push(tokio::spawn(async move {
            for cyc in 0..cycles {
                let start = origin + dur(cyc as f64 * cycle_len + offset);
                tokio::time::sleep_until(start).await;
                let w0 = canary.now_ns();
                let mut rows: Vec<Value> = Vec::with_capacity(pings);
                for n in 0..pings {
                    let slot = start + dur(interval * n as f64);
                    tokio::time::sleep_until(slot).await;
                    // Send-side observer effect: how late this task got to send vs its slot
                    // (tokio::time::Instant is the monotonic clock).
                    let send_lag = tokio::time::Instant::now().saturating_duration_since(slot).as_nanos() as i64;
                    let seq = (cyc * pings + n) as u16; // same numbering as Python: unique across cycles
                    let pr = ping(&sh, target, id, seq, dur(timeout)).await;
                    match pr.rx {
                        Some(rx) => rows.push(json!([seq, pr.tx_ns, rx.krx, rx.urx, null, rx.batch, rx.wakeup, send_lag])),
                        None => rows.push(json!([seq, pr.tx_ns, null, null, null, 0, 0, send_lag])),
                    }
                }
                let w1 = canary.now_ns();
                let win = canary.window(w0, w1);

                // ---- post-cycle "database write": semaphore -> CPU burn -> async I/O ----
                let t0 = Instant::now();
                let permit = sem.acquire().await.unwrap();
                let wait_ms = t0.elapsed().as_secs_f64() * 1000.0;
                let db_start = now_real_ns(); // CLOCK_REALTIME around the CPU work, for the burst shading
                burn(dur(db_ms / 1000.0)); // inline spin: blocks this worker thread
                let db_end = now_real_ns();
                tokio::time::sleep(dur(db_io_ms / 1000.0)).await; // still holding the permit, like Python
                drop(permit);

                sh.emit(json!({"e": "cycle", "ep": idx, "cyc": cyc, "target": target.to_string(), "icmp_id": id,
                    "db_wait_ms": (wait_ms * 1000.0).round() / 1000.0, "db_start_ns": db_start, "db_end_ns": db_end,
                    "canary": win, "packets": rows}));
            }
        }));
    }

    let all = async {
        for h in handles {
            let _ = h.await;
        }
    };
    if !stopped {
        tokio::select! {
            _ = all => {}
            _ = sigint.recv() => { stopped = true; }
            _ = sigterm.recv() => { stopped = true; }
        }
    }

    // Probing is over: freeze the canary BEFORE any summary work so it cannot pollute the numbers.
    canary.freeze();
    let cs = canary.all();
    ticker.abort();
    sh.emit(json!({"e": "summary", "sent": sh.sent.load(Ordering::Relaxed), "replied": sh.replied.load(Ordering::Relaxed),
        "reader_calls": sh.wakeups.load(Ordering::Relaxed), "unmatched": sh.unmatched.load(Ordering::Relaxed),
        "late": sh.late.load(Ordering::Relaxed), "canary": cs, "emit_us_total": r1(sh.emit_ns.load(Ordering::Relaxed) as f64 / 1e3),
        "emit_n": sh.emit_n.load(Ordering::Relaxed), "stopped": stopped}));
    std::process::exit(0);
}
