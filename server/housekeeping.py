"""Is everything closed properly?  Leftover probes, orphaned workers, NIC settings, memory.

A run is a separate probe process (and, in Python multi-core mode, its pool of worker processes). Normally
they all end with the run, and the dashboard waits for them when it shuts down. This module checks that
nothing was left behind anyway, e.g. after the dashboard was killed with ``kill -9``, a crash, or a power
cut, and reports how much memory the dashboard itself holds.

It is used three ways: at dashboard start-up (warnings in the terminal and a banner on the page), in the
shutdown report, and on demand::

    sudo .venv/bin/python -m server.app --check

Only processes whose working directory is this project are considered, so other programs that also use
Python's multiprocessing (GNS3, Jupyter, ...) are never mistaken for the lab's. Run it with sudo: a normal user
cannot see the working directory of root's processes, and dashboard runs are root's.
"""
from __future__ import annotations

import os
import socket
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent.parent

# How each kind of lab process shows up in /proc/<pid>/cmdline.
SIGNATURES = (("probe_lab.py", "--jsonl", "Python probe (dashboard run)"),
              ("probe_lab.py", None, "Python probe (terminal run)"),
              ("go_prober", None, "Go probe"),
              ("rust_prober", None, "Rust probe"),
              ("multiprocessing", "spawn_main", "Python multi-core ORM worker"))


def _cmdline(pid: int) -> List[str]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
    except OSError:
        return []


def _cwd(pid: int) -> Optional[str]:
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return None


def _status(pid) -> Dict[str, str]:
    out = {}
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                k, _, v = line.partition(":")
                out[k] = v.strip()
    except OSError:
        pass
    return out


def suspended(pid) -> bool:
    """True if the process is stopped (state T), e.g. by Ctrl-Z in its terminal. A stopped process keeps its memory
    and ports but cannot react to Ctrl-C or kill (SIGTERM) until it is resumed (SIGCONT, or `fg` in its terminal)."""
    return _status(pid).get("State", "").startswith("T")


def resume_hint(pid) -> str:
    return (f" It is SUSPENDED (Ctrl-Z was pressed in its terminal), so it cannot react to Ctrl-C or kill until resumed: "
            f"type `fg` in its terminal and press Ctrl-C, or run: sudo kill -CONT {pid}  (a kill sent earlier then takes effect).")


def rss_mb(pid: int | str = "self") -> Optional[float]:
    """Resident memory of a process in MB (VmRSS)."""
    v = _status(pid).get("VmRSS", "")  # type: ignore[arg-type]
    return round(int(v.split()[0]) / 1024, 1) if v else None


def lab_processes(exclude: Iterable[int] = ()) -> List[Dict[str, object]]:
    """Probe and worker processes of THIS project that are running now (excluding ``exclude``).

    Each entry: pid, parent pid, what it is, memory, and the command line. Unreadable processes (other users'
    without root) are skipped."""
    skip = set(exclude) | {os.getpid()}
    found = []
    root = str(ROOT)
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) in skip:
            continue
        pid = int(d)
        args = _cmdline(pid)
        if not args:
            continue
        joined = " ".join(args)
        kind = None
        for a, b, label in SIGNATURES:
            if a in joined and (b is None or b in joined):
                kind = label
                break
        if kind is None:
            continue
        cwd = _cwd(pid)
        if cwd is None or not (cwd == root or cwd.startswith(root + os.sep)):
            continue                                  # another program's process (or not ours to judge)
        st = _status(pid)
        found.append({"pid": pid, "ppid": int(st.get("PPid", "0") or 0), "kind": kind,
                      "rss_mb": rss_mb(pid), "cmd": joined[:160], "suspended": st.get("State", "").startswith("T")})
    return found


def nic_stamping_left_on() -> List[Dict[str, object]]:
    """Interfaces whose NIC receive timestamping is switched on right now.

    The Python engine switches it on only with --hw / the dashboard's checkbox and switches it back off at the
    end of the run, so finding it on after a session usually means a run was killed hard (kill -9, power cut),
    unless another program (e.g. the PTP daemon ptp4l) uses it on purpose."""
    from server import hw_timestamp as hw
    out = []
    for _idx, name in socket.if_nameindex():
        cfg = hw.HwtstampConfig()
        try:
            hw._ioctl(None, name, hw.SIOCGHWTSTAMP, cfg)
        except OSError:
            continue                                  # virtual interface, or no hardware stamping
        if cfg.rx_filter != hw.HWTSTAMP_FILTER_NONE:
            out.append({"interface": name, "rx_filter": cfg.rx_filter, "tx_type": cfg.tx_type})
    return out


def check(exclude: Iterable[int] = ()) -> Dict[str, object]:
    """Everything the start-up check and ``--check`` report, plus plain-language problems."""
    procs = lab_processes(exclude)
    nics = nic_stamping_left_on()
    problems = []
    for p in procs:
        orphan = p["ppid"] == 1 or not os.path.exists(f"/proc/{p['ppid']}")
        problems.append(f"{p['kind']} pid {p['pid']} is still running ({p['rss_mb']} MB)"
                        + (" with no parent: left over from an earlier session" if orphan else "")
                        + f". Stop it with: sudo kill {p['pid']}" + (resume_hint(p["pid"]) if p["suspended"] else ""))
    for n in nics:
        problems.append(f"{n['interface']}: NIC receive timestamping is ON (rx_filter={n['rx_filter']}). If no PTP daemon "
                        f"uses it, a Python run with hardware stamps was probably killed hard. Reset with: sudo "
                        f".venv/bin/python -c \"from server import hw_timestamp as h; h._ioctl(None, '{n['interface']}', "
                        f"h.SIOCSHWTSTAMP, h.HwtstampConfig(0, 0, 0))\"")
    return {"processes": procs, "nic_stamping_on": nics, "problems": problems}


def port_owner(port: int) -> Optional[Dict[str, object]]:
    """Which process is listening on this TCP port: pid, start time and command line (None if not found).

    /proc/net/tcp(6) lists listening sockets with their inode; the owner is the process with an open file descriptor
    pointing at that socket inode. Seeing another user's (e.g. root's) descriptors needs root."""
    inodes = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(table) as f:
                for line in f.readlines()[1:]:
                    cols = line.split()
                    if cols[3] == "0A" and int(cols[1].rsplit(":", 1)[1], 16) == port:     # 0A = LISTEN
                        inodes.add(cols[9])
        except OSError:
            continue
    if not inodes:
        return None
    targets = {f"socket:[{i}]" for i in inodes}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            for fd in os.listdir(f"/proc/{d}/fd"):
                if os.readlink(f"/proc/{d}/fd/{fd}") in targets:
                    started = time.strftime("%H:%M:%S", time.localtime(os.stat(f"/proc/{d}").st_mtime))
                    return {"pid": int(d), "cmd": " ".join(_cmdline(int(d)))[:120], "started": started,
                            "suspended": suspended(int(d))}
        except OSError:
            continue
    return None
