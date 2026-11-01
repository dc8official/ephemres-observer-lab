"""Host conditions recorded with every run: the things on THIS machine that move the numbers.

The lab measures microseconds, so the state of the prober host matters as much as the code.
None of this is changed by the lab; it is only read and saved (``meta.json`` -> ``host``) and
turned into plain-language warnings, so two runs can be checked for "same conditions" later.

What is recorded and why
------------------------
* CPU frequency governor of the probe core ("powersave" lets the clock speed drift, so the same
  work takes a different time from run to run; "performance" holds it steady).
* CPU sleep states (C-states).  An idle core powers parts of itself down; waking from a deep
  state takes tens to hundreds of microseconds.  A LIGHTLY loaded run (e.g. widely staggered)
  lets the core sleep deeper between packets, so its wake-up floor can look WORSE than a busier
  run's.  The exit latency of the deepest enabled state is the size of that effect.
* Turbo / boost: frequency that depends on temperature and on what other cores are doing.
* SMT sibling: with hyper-threading two logical CPUs share one physical core, so anything
  running on the sibling slows the probe core down.
* NIC interrupts: which cores may handle the network card's interrupts.  If one of them is the
  probe's core, packet processing and the measured program take turns on the same CPU.
* NIC interrupt coalescing (``ethtool -c``): the card waits a little to batch interrupts.  That
  delays Clock A (the kernel stamp) a bit, i.e. it affects kernel RTT, not observer lag.
* Load average and isolated CPUs: how busy the rest of the machine was.

Everything is best effort: a missing file (virtual machine, container, other kernel) just leaves
that field out.  Reading these files needs no root, except some NIC details.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from typing import Any, Dict, Iterable, List, Optional

CPU = "/sys/devices/system/cpu"
DEEP_SLEEP_US = 50          # an enabled C-state slower than this to wake from is worth a warning
BUSY_LOAD = 1.0             # 1-minute load average above this = other programs are competing


def _read(path: str) -> Optional[str]:
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return None


def _cpu_info(core: Optional[int]) -> Dict[str, Any]:
    """CPU model, governor, turbo, sleep states and hyper-threading sibling of the probe core."""
    out: Dict[str, Any] = {}
    cpuinfo = _read("/proc/cpuinfo") or ""
    m = re.search(r"^model name\s*:\s*(.+)$", cpuinfo, re.M)
    if m:
        out["model"] = m.group(1).strip()
    out["logical_cpus"] = os.cpu_count()
    no_turbo = _read(f"{CPU}/intel_pstate/no_turbo")
    boost = _read(f"{CPU}/cpufreq/boost")
    if no_turbo is not None:
        out["turbo"] = no_turbo == "0"
    elif boost is not None:
        out["turbo"] = boost == "1"
    out["isolated_cpus"] = _read(f"{CPU}/isolated") or ""
    out["clocksource"] = _read("/sys/devices/system/clocksource/clocksource0/current_clocksource")
    if core is None:
        return out
    base = f"{CPU}/cpu{core}"
    out["probe_core"] = core
    out["governor"] = _read(f"{base}/cpufreq/scaling_governor")
    out["freq_driver"] = _read(f"{base}/cpufreq/scaling_driver")
    out["smt_siblings"] = _read(f"{base}/topology/thread_siblings_list")
    states = []
    idle_dir = f"{base}/cpuidle"
    if os.path.isdir(idle_dir):
        for d in sorted(os.listdir(idle_dir), key=lambda x: int(x[5:]) if x[5:].isdigit() else 0):
            if not d.startswith("state"):
                continue
            states.append({"name": _read(f"{idle_dir}/{d}/name"),
                           "exit_latency_us": int(_read(f"{idle_dir}/{d}/latency") or 0),
                           "enabled": _read(f"{idle_dir}/{d}/disable") == "0"})
    out["cstates"] = states
    return out


def _irqs_for(iface: str) -> List[Dict[str, Any]]:
    """Interrupt lines whose name mentions the interface, with the cores allowed to serve them."""
    irqs = []
    for line in (_read("/proc/interrupts") or "").splitlines()[1:]:
        if iface not in line:
            continue
        num = line.split(":", 1)[0].strip()
        if num.isdigit():
            irqs.append({"irq": int(num), "cpus": _read(f"/proc/irq/{num}/smp_affinity_list")})
    return irqs


def _expand(cpu_list: Optional[str]) -> set:
    """'0-3,6' -> {0, 1, 2, 3, 6}"""
    cpus = set()
    for part in filter(None, (cpu_list or "").split(",")):
        a, _, b = part.partition("-")
        if a.isdigit():
            cpus.update(range(int(a), int(b) + 1) if b.isdigit() else [int(a)])
    return cpus


def _coalescing(iface: str) -> Dict[str, str]:
    tool = shutil.which("ethtool")
    if not tool:
        return {}
    try:
        text = subprocess.run([tool, "-c", iface], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    keep = ("Adaptive RX", "rx-usecs", "rx-frames")
    out = {}
    for line in text.splitlines():
        key, _, val = line.partition(":")
        if key.strip().startswith(keep) and val.strip() and not val.strip().startswith("n/a"):
            out[key.strip()] = val.strip()
    return out


def _nic_info(iface: str) -> Dict[str, Any]:
    dev = f"/sys/class/net/{iface}"
    drv = os.path.realpath(f"{dev}/device/driver") if os.path.exists(f"{dev}/device/driver") else None
    return {"interface": iface, "driver": os.path.basename(drv) if drv else "virtual",
            "speed_mbps": _read(f"{dev}/speed"), "irqs": _irqs_for(iface), "coalescing": _coalescing(iface)}


def collect(interfaces: Iterable[str], probe_core: Optional[int]) -> Dict[str, Any]:
    """Snapshot of the host conditions, plus ``warnings``: plain sentences about what may skew results."""
    info: Dict[str, Any] = {"kernel": platform.release(), "cpu": _cpu_info(probe_core),
                            "nics": [_nic_info(i) for i in sorted(set(interfaces)) if i and i != "?"]}
    try:
        info["load_avg_1m"] = round(os.getloadavg()[0], 2)
    except OSError:
        pass
    info["warnings"] = warnings(info)
    return info


def warnings(info: Dict[str, Any]) -> List[str]:
    """Plain-language warnings about host settings that can make runs slower or less repeatable."""
    cpu, out = info.get("cpu", {}), []
    core = cpu.get("probe_core")
    gov = cpu.get("governor")
    if gov and gov != "performance":
        out.append(f"CPU governor on core {core} is '{gov}': clock speed can vary between runs "
                   f"('performance' keeps it steady)")
    deep = [s for s in cpu.get("cstates", []) if s["enabled"] and s["exit_latency_us"] > DEEP_SLEEP_US]
    if deep:
        worst = max(deep, key=lambda s: s["exit_latency_us"])
        out.append(f"deep CPU sleep state {worst['name']} is enabled (wake-up takes ~{worst['exit_latency_us']} µs): "
                   f"lightly loaded runs can show a higher wake-up floor than busy ones")
    if cpu.get("turbo"):
        out.append("turbo/boost is on: clock speed depends on temperature and on the other cores' load")
    sib = cpu.get("smt_siblings")
    if core is not None and sib and _expand(sib) - {core}:
        out.append(f"core {core} shares a physical core with CPU {','.join(map(str, sorted(_expand(sib) - {core})))} "
                   f"(hyper-threading): work there slows the probe")
    load = info.get("load_avg_1m")
    if load is not None and load > BUSY_LOAD:
        out.append(f"1-minute load average is {load}: other programs were competing for the CPUs")
    for nic in info.get("nics", []):
        if core is not None and any(core in _expand(i["cpus"]) for i in nic["irqs"]):
            out.append(f"{nic['interface']} interrupts may run on the probe core {core}: packet handling and "
                       f"the measured program take turns on one CPU")
        if nic.get("coalescing", {}).get("Adaptive RX", "").startswith("on"):
            out.append(f"{nic['interface']} uses adaptive interrupt coalescing: the kernel stamp (Clock A) "
                       f"shifts with traffic load (affects kernel RTT, not observer lag)")
    return out
