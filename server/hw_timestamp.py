"""Optional NIC hardware timestamping (the SIOCSHWTSTAMP ioctl) for Clock A.

The lab's Clock A is the kernel's arrival timestamp.  On a real NIC the kernel
can ALSO record the NIC's own hardware timestamp, taken by the network chip when
the frame arrives.  This module switches that feature on, if the NIC supports it.

Why it is optional: virtual interfaces (lo, veth, GNS3 taps, VMs) have no
hardware clock.  There the ioctl fails and we carry on with software timestamps,
which is all the observer-lag measurement needs.  Hardware stamps are recorded
(as ``hw_rx_ns``) only so you can cross-check them against tcpdump.

The two clocks are different clocks:
  * software stamps are CLOCK_REALTIME nanoseconds (the system clock);
  * hardware stamps are nanoseconds of the NIC's own PTP hardware clock, which
    usually starts at an arbitrary value, so never subtract one kind from the other.

THIS IS A HOST-WIDE SETTING, SO WE PUT IT BACK
----------------------------------------------
Unlike a setsockopt, SIOCSHWTSTAMP changes the network card itself: every
program on the machine sees the new setting, and it survives our exit.  A PTP
daemon (ptp4l) on the same NIC could be disturbed.  So we follow three rules:
  1. Read the current setting first (SIOCGHWTSTAMP).  If the driver cannot tell
     us what it is, we cannot restore it, so we leave the NIC alone.
  2. If something else has already switched receive stamping on, leave it alone
     too (it is not ours to change).
  3. If we did change it, ``restore_hw_timestamping`` puts the old value back when
     the socket closes.  (Only a hard kill, e.g. SIGKILL, can skip that step.)

How the ioctl works.  ``ioctl(fd, request, arg)`` is the old Unix "device-specific
syscall".  For network ioctls the argument is a ``struct ifreq``, a 40-byte record:

    offset 0   char  ifr_name[16]   interface name, e.g. "enp0s31f6"
    offset 16  union (24 bytes)     here: a pointer to our ``struct hwtstamp_config``

The kernel reads the 12-byte hwtstamp_config (three 32-bit ints) from that pointer,
asks the NIC driver to apply it, and writes back what the driver actually granted.
SIOCGHWTSTAMP uses the same layout but only fills the struct in.
Requires CAP_NET_ADMIN (root).
"""
from __future__ import annotations

import ctypes
import errno
import fcntl
import socket
import struct
from dataclasses import dataclass
from typing import Optional, Tuple

# Values copied from the kernel headers (Linux x86_64).
SIOCSHWTSTAMP = 0x89B0            # ioctl request: set hardware timestamping configuration
SIOCGHWTSTAMP = 0x89B1            # ioctl request: read the current configuration (Linux 3.14+)
HWTSTAMP_TX_OFF = 0               # do not timestamp transmitted frames (we only need receive stamps)
HWTSTAMP_FILTER_NONE = 0          # receive stamping off
HWTSTAMP_FILTER_ALL = 1           # timestamp every received frame

SO_TIMESTAMPING = 37              # setsockopt option: choose which timestamps the socket receives
SCM_TIMESTAMPING = SO_TIMESTAMPING  # the control-message type that carries them has the same number

# Bit flags for SO_TIMESTAMPING.  Two kinds: "generate" (RX_*) and "report to me" (SOFTWARE, RAW_HARDWARE).
SOF_TIMESTAMPING_RX_HARDWARE = 1 << 2
SOF_TIMESTAMPING_RX_SOFTWARE = 1 << 3
SOF_TIMESTAMPING_SOFTWARE = 1 << 4
SOF_TIMESTAMPING_RAW_HARDWARE = 1 << 6

IFNAMSIZ = 16
IFREQ_SIZE = 40                   # sizeof(struct ifreq) on x86_64: 16 name + 24 union


class HwtstampConfig(ctypes.Structure):
    """struct hwtstamp_config from <linux/net_tstamp.h>: three 32-bit ints, 12 bytes."""
    _fields_ = [
        ("flags", ctypes.c_int),      # reserved, must be 0
        ("tx_type", ctypes.c_int),    # HWTSTAMP_TX_*
        ("rx_filter", ctypes.c_int),  # HWTSTAMP_FILTER_*
    ]


@dataclass
class HwTimestampStatus:
    interface: str
    hardware: bool                    # True if receive hardware stamps should now arrive
    reason: str
    rx_filter_granted: Optional[int] = None
    # The configuration that was in place before we changed it, as (flags, tx_type, rx_filter).
    # None means we did not change anything, so there is nothing to restore.
    previous: Optional[Tuple[int, int, int]] = None

    def describe(self) -> str:
        mode = "hardware + software" if self.hardware else "software only"
        return f"[{self.interface}] timestamping: {mode} ({self.reason})"


def _why(exc: OSError) -> str:
    if exc.errno in (errno.EPERM, errno.EACCES):
        return "needs CAP_NET_ADMIN (run as root)"
    if exc.errno in (errno.EOPNOTSUPP, errno.ENOTTY, errno.EINVAL):
        return "this interface has no hardware timestamping (virtual interface?)"
    if exc.errno == errno.ENODEV:
        return "no such interface"
    if exc.errno == errno.ERANGE:
        return "the driver rejected the requested receive filter"
    return f"ioctl failed: {exc}"


def _ioctl(sock: Optional[socket.socket], interface: str, request: int, cfg: HwtstampConfig) -> None:
    """Run SIOCGHWTSTAMP / SIOCSHWTSTAMP for ``interface``; the kernel reads/writes ``cfg`` in place."""
    # Pack the 16-byte name and the address of cfg (cfg must stay alive until the ioctl returns).
    ifreq = struct.pack("@16sP", interface.encode()[:IFNAMSIZ - 1], ctypes.addressof(cfg))
    ifreq = ifreq.ljust(IFREQ_SIZE, b"\0")
    own_sock = sock is None
    s = sock or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)   # any socket works as the ioctl handle
    try:
        fcntl.ioctl(s.fileno(), request, ifreq)
    finally:
        if own_sock:
            s.close()


def configure_hw_timestamping(interface: str, sock: Optional[socket.socket] = None) -> HwTimestampStatus:
    """Ask the NIC driver to start timestamping received frames.  Never raises on failure."""
    # Rule 1: learn the current setting, or do not touch the NIC at all.
    cur = HwtstampConfig()
    try:
        _ioctl(sock, interface, SIOCGHWTSTAMP, cur)
    except OSError as exc:
        if exc.errno in (errno.EOPNOTSUPP, errno.ENOTTY, errno.EINVAL):
            return HwTimestampStatus(interface, False, "current setting cannot be read (SIOCGHWTSTAMP), "
                                                       "so the NIC was left untouched")
        return HwTimestampStatus(interface, False, _why(exc))

    # Rule 2: receive stamping is already on (another program, or a previous run that was killed).
    if cur.rx_filter != HWTSTAMP_FILTER_NONE:
        return HwTimestampStatus(interface, cur.rx_filter == HWTSTAMP_FILTER_ALL,
                                 f"already enabled by someone else (rx_filter={cur.rx_filter}); left untouched",
                                 cur.rx_filter)

    previous = (cur.flags, cur.tx_type, cur.rx_filter)
    cfg = HwtstampConfig(flags=0, tx_type=cur.tx_type, rx_filter=HWTSTAMP_FILTER_ALL)  # keep TX as it was
    try:
        _ioctl(sock, interface, SIOCSHWTSTAMP, cfg)
    except OSError as exc:
        return HwTimestampStatus(interface, False, _why(exc))
    # The driver writes back what it really granted.  Some upgrade a request (e.g. to a
    # superset filter); some downgrade it to PTP packets only, which never matches ICMP.
    granted = cfg.rx_filter
    if granted == HWTSTAMP_FILTER_NONE:
        return HwTimestampStatus(interface, False, "driver granted no receive filter", granted, previous)
    return HwTimestampStatus(interface, True, f"SIOCSHWTSTAMP accepted, rx_filter={granted}; "
                                              f"restored on exit", granted, previous)


def restore_hw_timestamping(status: HwTimestampStatus, sock: Optional[socket.socket] = None) -> Optional[str]:
    """Put back the configuration ``configure_hw_timestamping`` replaced.  Returns an error text or None."""
    if status.previous is None:
        return None
    flags, tx_type, rx_filter = status.previous
    try:
        _ioctl(sock, status.interface, SIOCSHWTSTAMP, HwtstampConfig(flags=flags, tx_type=tx_type, rx_filter=rx_filter))
    except OSError as exc:
        return f"[{status.interface}] could not restore hardware timestamping: {_why(exc)}"
    status.previous = None
    return None
