"""Raw ICMP socket with kernel receive timestamps ("Clock A") + user-space time ("Clock B").

HOW A PING REPLY TRAVELS
----------------------------------------
1. The reply frame arrives at the NIC.  The driver hands it to the kernel,
   which - at that moment - reads the clock and writes the time into the
   packet's kernel buffer (an "skb").  THIS is Clock A.
2. The kernel appends the packet to our socket's receive queue (a kernel-memory
   FIFO, sized by SO_RCVBUF).  The packet now just WAITS there.
3. epoll tells asyncio "the socket is readable".  asyncio can only act on that
   when the currently running Python code yields back to the event loop.  If
   some coroutine is busy burning CPU (our simulated ORM work) the packet sits
   in the queue, aging, while its Clock-A stamp stays frozen.
4. Finally the loop calls our reader, we call recvmsg_into(), and read the
   clock again in Python.  THIS is Clock B.

        Observer lag  =  Clock B - Clock A   (time the packet waited for Python)

Both clocks are CLOCK_REALTIME nanoseconds, so they subtract directly.

WHERE THE KERNEL STAMP COMES FROM: THE cmsg
-------------------------------------------
recvmsg() has two output buffers: the data buffer (the packet bytes) and a
separate *ancillary* buffer holding "control messages" (cmsg).  Each cmsg is a
small header ``{len, level, type}`` followed by a payload.  When we ask for
timestamps the kernel adds one with level=SOL_SOCKET and either:

* type SCM_TIMESTAMPING (37): payload = ``struct scm_timestamping`` = three
  ``struct timespec`` (each = int64 tv_sec + int64 tv_nsec on x86_64):
  ``[0]`` software stamp, ``[1]`` legacy/unused, ``[2]`` raw NIC-hardware stamp.
* type SCM_TIMESTAMPNS (35): payload = one ``struct timespec``  (older, simpler API).
Python's recvmsg_into returns them as ``(level, type, payload_bytes)`` tuples.

PREALLOCATED BUFFER
-------------------
``recvmsg_into([buf], 1024)`` writes the packet straight into one reusable
1500-byte bytearray, so the hot path allocates no per-packet data buffer
(only the small ancillary tuple list Python builds).
"""
from __future__ import annotations

import fcntl
import socket
import struct
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from server.hw_timestamp import (
    SCM_TIMESTAMPING, SO_TIMESTAMPING, SOF_TIMESTAMPING_RAW_HARDWARE,
    SOF_TIMESTAMPING_RX_HARDWARE, SOF_TIMESTAMPING_RX_SOFTWARE,
    SOF_TIMESTAMPING_SOFTWARE, HwTimestampStatus, configure_hw_timestamping, restore_hw_timestamping,
)

SO_TIMESTAMPNS = 35
SO_RCVBUFFORCE = 33
SCM_TIMESTAMPNS = 35
SIOCGIFADDR = 0x8915
ICMP_ECHO_REPLY, ICMP_ECHO_REQUEST = 0, 8
SOL_RAW, ICMP_FILTER = 255, 1
RX_BUF_SIZE = 1500
ANC_BUF_SIZE = 1024
PAYLOAD_LEN = 56

_TS3 = struct.Struct("=6q")     # three timespecs
_TS1 = struct.Struct("=2q")     # one timespec


# ---------------------------------------------------------------------------
# Route auto-discovery: which interface / source IP reaches this target?
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RouteInfo:
    target: str
    interface: str
    src_ip: str


def discover_route(target: str) -> RouteInfo:
    """Ask the kernel's routing table, without sending anything.

    connect() on a UDP socket does not transmit; it only makes the kernel run a
    route lookup and pick the source address.  getsockname() reveals the
    answer.  We then map that source IP back to an interface name with
    SIOCGIFADDR ("what is the IPv4 address of interface X?") over all NICs.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((target, 9))
        src_ip = s.getsockname()[0]
        for _idx, name in socket.if_nameindex():
            try:
                req = struct.pack("256s", name.encode()[:15])
                res = fcntl.ioctl(s.fileno(), SIOCGIFADDR, req)
                if socket.inet_ntoa(res[20:24]) == src_ip:
                    return RouteInfo(target, name, src_ip)
            except OSError:
                continue             # interface has no IPv4 address
    return RouteInfo(target, "?", src_ip)


# ---------------------------------------------------------------------------
# ICMP packet construction
# ---------------------------------------------------------------------------
def icmp_checksum(data: bytes) -> int:
    """RFC 1071 checksum.  On SOCK_RAW the kernel adds the IP header but NOT this."""
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


def build_echo_request(icmp_id: int, seq: int) -> bytes:
    """Type 8 / code 0 + checksum + id + seq + 56 payload bytes.

    RFC 792: the responder MUST copy id, seq and payload into its Echo Reply.
    That guarantee is what lets one socket serve hundreds of virtual endpoints.
    """
    payload = (b"EPHEMRES" + struct.pack("!HH", icmp_id, seq)).ljust(PAYLOAD_LEN, b"\xa5")
    csum = icmp_checksum(struct.pack("!BBHHH", ICMP_ECHO_REQUEST, 0, 0, icmp_id, seq) + payload)
    return struct.pack("!BBHHH", ICMP_ECHO_REQUEST, 0, csum, icmp_id, seq) + payload


# ---------------------------------------------------------------------------
# The socket
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Reception:
    icmp_id: int
    icmp_seq: int
    src_ip: str
    kernel_ns: Optional[int]    # Clock A: CLOCK_REALTIME ns at kernel arrival (None if unavailable)
    hw_ns: Optional[int]        # NIC hardware clock ns (different clock domain!), if supported
    user_real_ns: int           # Clock B: CLOCK_REALTIME ns right after recvmsg_into
    user_mono_ns: int           # same instant on CLOCK_MONOTONIC

    @property
    def observer_lag_ns(self) -> Optional[int]:
        return None if self.kernel_ns is None else self.user_real_ns - self.kernel_ns


class KernelClockSocket:
    def __init__(self, routes: List[RouteInfo], want_hw: bool = True):
        self.routes = routes
        self.want_hw = want_hw
        self.sock: Optional[socket.socket] = None
        self.mode = "none"                      # description of what was enabled
        self.notes: List[str] = []
        self._hw: List[HwTimestampStatus] = []  # NICs we reconfigured; restored by close()
        self._buf = bytearray(RX_BUF_SIZE)      # reused for every packet
        self._view = memoryview(self._buf)

    def open(self) -> socket.socket:
        """Open the raw ICMP socket: non-blocking, Echo Replies only, with kernel (and optionally NIC) receive stamps."""
        s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        s.setblocking(False)
        # Kernel-side filter so Python never wakes for anything but Echo Replies.
        # struct icmp_filter: bit N set => BLOCK ICMP type N.
        s.setsockopt(SOL_RAW, ICMP_FILTER, struct.pack("=I", ~(1 << ICMP_ECHO_REPLY) & 0xFFFFFFFF))
        # Big receive queue: while the event loop is busy, replies pile up here.  If the queue
        # overflows the kernel silently drops them, which would look like packet loss.
        # A normal SO_RCVBUF request is capped at net.core.rmem_max (often only ~208 KiB);
        # SO_RCVBUFFORCE (root only) bypasses that cap, so try it first.
        for opt in (SO_RCVBUFFORCE, socket.SO_RCVBUF):
            try:
                s.setsockopt(socket.SOL_SOCKET, opt, 8 * 1024 * 1024)
                break
            except OSError:
                continue
        # The kernel reports twice the requested size (it counts its own bookkeeping overhead).
        self.notes.append(f"receive queue: {s.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF) // 1024} KiB")

        flags = SOF_TIMESTAMPING_RX_SOFTWARE | SOF_TIMESTAMPING_SOFTWARE
        hw_ok = False
        if self.want_hw:
            # Optional NIC hardware stamping via SIOCSHWTSTAMP (needs root; silently
            # falls back on virtual NICs such as lo / veth / GNS3 taps).
            for iface in sorted({r.interface for r in self.routes if r.interface != "?"}):
                st = configure_hw_timestamping(iface, s)
                self._hw.append(st)
                hw_ok |= st.hardware
                self.notes.append(st.describe())
            if hw_ok:
                flags |= SOF_TIMESTAMPING_RX_HARDWARE | SOF_TIMESTAMPING_RAW_HARDWARE
        try:
            s.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPING, flags)
            self.mode = "SO_TIMESTAMPING " + ("software+hardware" if hw_ok else "software")
        except OSError:
            s.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPNS, 1)       # older API
            self.mode = "SO_TIMESTAMPNS (software)"
        self.sock = s
        return s

    def close(self) -> None:
        # SIOCSHWTSTAMP changed the NIC for the whole host: put the previous setting back.
        for st in self._hw:
            err = restore_hw_timestamping(st, self.sock)
            if err:
                print(f"WARNING: {err}", file=sys.stderr)   # nobody reads notes after close
        self._hw.clear()
        if self.sock:
            self.sock.close()
            self.sock = None

    def send_echo(self, target: str, icmp_id: int, seq: int) -> int:
        """Send one echo request; return the CLOCK_REALTIME ns just before sendto()."""
        pkt = build_echo_request(icmp_id, seq)
        tx = time.clock_gettime_ns(time.CLOCK_REALTIME)
        self.sock.sendto(pkt, (target, 0))
        return tx

    def recv_one(self) -> Optional[Reception]:
        """Read one packet.  Returns None if the queue is empty or packet is irrelevant."""
        # Raises BlockingIOError when the queue is empty (caller's stop signal).
        n, anc, _flags, addr = self.sock.recvmsg_into([self._view], ANC_BUF_SIZE)
        # ---- Clock B: the very first thing after the syscall returns ----
        user_real = time.clock_gettime_ns(time.CLOCK_REALTIME)
        user_mono = time.monotonic_ns()

        kernel_ns = hw_ns = None
        for level, ctype, data in anc:
            if level != socket.SOL_SOCKET:
                continue
            if ctype == SCM_TIMESTAMPING and len(data) >= 48:
                s0, n0, _s1, _n1, s2, n2 = _TS3.unpack_from(data)
                kernel_ns = s0 * 1_000_000_000 + n0 if (s0 or n0) else None
                hw_ns = s2 * 1_000_000_000 + n2 if (s2 or n2) else None
            elif ctype == SCM_TIMESTAMPNS and len(data) >= 16:
                s0, n0 = _TS1.unpack_from(data)
                kernel_ns = s0 * 1_000_000_000 + n0

        # Raw sockets deliver the IP header too; its length is in the low nibble of byte 0.
        if n < 20:
            return None
        ihl = (self._buf[0] & 0x0F) * 4
        if n < ihl + 8 or self._buf[ihl] != ICMP_ECHO_REPLY:
            return None
        rid, rseq = struct.unpack_from("!HH", self._buf, ihl + 4)
        return Reception(rid, rseq, addr[0], kernel_ns, hw_ns, user_real, user_mono)
