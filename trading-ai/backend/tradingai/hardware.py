"""Computer health: temperature and thermal throttling, read from the operating system's own sensors.

Windows 10 and 11: Performance Data Helper (pdh.dll) counters through ctypes. English counter names work on every
Windows language, and none of them needs administrator rights:
  \\Thermal Zone Information(*)\\High Precision Temperature   tenths of a kelvin (ACPI thermal zones)
  \\Thermal Zone Information(*)\\Temperature                  kelvin (older Windows builds)
  \\Thermal Zone Information(*)\\% Passive Limit              100 = not limited; lower = Windows is slowing the CPU to
                                                             cool it (passive cooling, i.e. thermal throttling)
  \\Thermal Zone Information(*)\\Throttle Reasons             0 = none reported
  \\Processor Information(_Total)\\% Processor Time           load
  \\Processor Information(_Total)\\% Processor Performance    speed vs nominal (above 100 = boosting)
  \\Processor Information(_Total)\\Processor Frequency        nominal MHz
  \\Processor Information(_Total)\\Performance Limit Flags    non-zero = the CPU is being held below its normal speed
Linux: /sys/class/thermal and /sys/class/hwmon, /proc/stat for load.

Many desktop PCs expose no thermal zone at all, and an ACPI zone is often the motherboard, not the CPU core. Nothing
is invented: a value the machine does not report is None and is shown as "not reported". The load test also measures
the work rate itself, which falls when a CPU throttles, so throttling can be seen even without a temperature sensor.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from tradingai.app import App

WARN_C = 85.0              # sustained CPU temperatures above this deserve attention (most CPUs throttle near 95-100)
CRIT_C = 95.0              # the load test stops immediately at or above this
SAME_SENSOR_LIMITS = (5.0, 130.0)  # readings outside this range are sensor errors, not temperatures
PERF_LOW_PCT = 60.0        # effective speed below this while busy = held back
RATE_DROP_WARN = 0.30      # work rate falling more than 30% under sustained load = throttling (some fall is normal)

PDH_PATHS = {
    "zone_temp_hp": r"\Thermal Zone Information(*)\High Precision Temperature",
    "zone_temp": r"\Thermal Zone Information(*)\Temperature",
    "zone_passive": r"\Thermal Zone Information(*)\% Passive Limit",
    "zone_throttle": r"\Thermal Zone Information(*)\Throttle Reasons",
    "cpu_load": r"\Processor Information(_Total)\% Processor Time",
    "cpu_perf": r"\Processor Information(_Total)\% Processor Performance",
    "cpu_mhz": r"\Processor Information(_Total)\Processor Frequency",
    "cpu_limit": r"\Processor Information(_Total)\Performance Limit Flags",
    "cpu_load_basic": r"\Processor(_Total)\% Processor Time",
}


def windows_version() -> Optional[dict]:
    """Windows 11 reports itself as 10.0 with a build number of 22000 or higher."""
    if os.name != "nt":
        return None
    v = sys.getwindowsversion()
    name = "Windows 11" if v.major == 10 and v.build >= 22000 else f"Windows {v.major}"
    return {"name": name, "build": v.build, "version": f"{v.major}.{v.minor}.{v.build}"}


def cpu_name() -> Optional[str]:
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except OSError:
            return os.environ.get("PROCESSOR_IDENTIFIER")
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


def machine() -> dict:
    return {"os": platform.platform(), "windows": windows_version(), "cpu": cpu_name(), "logical_cpus": os.cpu_count(),
            "python": platform.python_version()}


# ---------------------------------------------------------------- Windows: PDH through ctypes
WILDCARD = {"zone_temp_hp", "zone_temp", "zone_passive", "zone_throttle"}     # one value per thermal zone


def _is_wine() -> bool:
    """Wine runs Windows programs on Linux; its pdh.dll lacks the array call and aborts the process if it is used."""
    try:
        import ctypes
        return hasattr(ctypes.WinDLL("ntdll.dll"), "wine_get_version")
    except (OSError, AttributeError):
        return False


class _Pdh:
    PDH_MORE_DATA = 0x800007D2
    FMT = 0x00000200 | 0x00008000           # PDH_FMT_DOUBLE | PDH_FMT_NOCAP100 (speed can be above 100%)

    def __init__(self, paths: dict[str, str]):
        import ctypes
        from ctypes import wintypes

        class Value(ctypes.Structure):
            _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]

        class Item(ctypes.Structure):
            _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", Value)]
        self.ct, self.Item = ctypes, Item
        pdh = ctypes.WinDLL("pdh.dll")
        pdh.PdhOpenQueryW.argtypes = [ctypes.c_wchar_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_void_p)]
        pdh.PdhAddEnglishCounterW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_size_t,
                                              ctypes.POINTER(ctypes.c_void_p)]
        pdh.PdhCollectQueryData.argtypes = [ctypes.c_void_p]
        pdh.PdhGetFormattedCounterArrayW.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                                     ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        pdh.PdhGetFormattedCounterValue.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                                    ctypes.POINTER(Value)]
        pdh.PdhCloseQuery.argtypes = [ctypes.c_void_p]
        for f in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData", "PdhGetFormattedCounterArrayW",
                  "PdhGetFormattedCounterValue", "PdhCloseQuery"):
            getattr(pdh, f).restype = wintypes.DWORD
        self.pdh, self.DWORD, self.Value = pdh, wintypes.DWORD, Value
        self.wine = _is_wine()
        self.q = ctypes.c_void_p()
        rc = pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.q))
        if rc != 0:
            raise OSError(f"PdhOpenQueryW failed ({rc:#x})")
        self.counters: dict[str, Any] = {}
        self.missing: dict[str, str] = {}
        for key, path in paths.items():
            if self.wine and key in WILDCARD:
                self.missing[key] = "not available under Wine"
                continue
            h = ctypes.c_void_p()
            rc = pdh.PdhAddEnglishCounterW(self.q, path, 0, ctypes.byref(h))
            if rc == 0:
                self.counters[key] = h
            else:
                self.missing[key] = f"{rc:#010x}"
        pdh.PdhCollectQueryData(self.q)              # rate counters (load, speed) need two collections

    def read(self) -> dict[str, dict[str, float]]:
        ct = self.ct
        self.pdh.PdhCollectQueryData(self.q)
        out: dict[str, dict[str, float]] = {}
        for key, h in self.counters.items():
            if key not in WILDCARD:                           # one instance (_Total): the single-value call
                val = self.Value()
                if self.pdh.PdhGetFormattedCounterValue(h, self.FMT, None, ct.byref(val)) == 0 and \
                        val.CStatus in (0, 1):
                    out[key] = {"_Total": float(val.doubleValue)}
                continue
            size, count = self.DWORD(0), self.DWORD(0)
            rc = self.pdh.PdhGetFormattedCounterArrayW(h, self.FMT, ct.byref(size), ct.byref(count), None)
            if rc != self.PDH_MORE_DATA or size.value == 0:
                continue
            buf = (ct.c_byte * size.value)()
            rc = self.pdh.PdhGetFormattedCounterArrayW(h, self.FMT, ct.byref(size), ct.byref(count), buf)
            if rc != 0:
                continue
            items = ct.cast(buf, ct.POINTER(self.Item))
            vals = {}
            for i in range(count.value):
                it = items[i]
                if it.FmtValue.CStatus in (0, 1):       # PDH_CSTATUS_VALID_DATA, PDH_CSTATUS_NEW_DATA
                    vals[it.szName or "_"] = float(it.FmtValue.doubleValue)
            if vals:
                out[key] = vals
        return out

    def close(self) -> None:
        if self.q:
            self.pdh.PdhCloseQuery(self.q)
            self.q = self.ct.c_void_p()


# ---------------------------------------------------------------- Linux: sysfs and /proc
class _Sysfs:
    def __init__(self, root: str = "/"):
        self.root = Path(root)
        self._cpu: Optional[tuple[int, int]] = None

    def _load(self) -> Optional[float]:
        try:
            parts = (self.root / "proc/stat").read_text().splitlines()[0].split()[1:]
            vals = [int(x) for x in parts]
        except (OSError, ValueError, IndexError):
            return None
        idle, total = vals[3] + (vals[4] if len(vals) > 4 else 0), sum(vals)
        prev, self._cpu = self._cpu, (idle, total)
        if prev is None or total == prev[1]:
            return None
        return round(100.0 * (1 - (idle - prev[0]) / (total - prev[1])), 1)

    def read(self) -> tuple[list[dict], Optional[float]]:
        sensors = []
        for z in sorted((self.root / "sys/class/thermal").glob("thermal_zone*")):
            try:
                t = int((z / "temp").read_text().strip()) / 1000.0
                kind = (z / "type").read_text().strip()
            except (OSError, ValueError):
                continue
            sensors.append({"name": f"{z.name} ({kind})", "source": "thermal zone", "temp_c": round(t, 1)})
        for hw in sorted((self.root / "sys/class/hwmon").glob("hwmon*")):
            try:
                name = (hw / "name").read_text().strip()
            except OSError:
                name = hw.name
            for f in sorted(hw.glob("temp*_input")):
                try:
                    t = int(f.read_text().strip()) / 1000.0
                except (OSError, ValueError):
                    continue
                label = f.with_name(f.name.replace("_input", "_label"))
                lab = label.read_text().strip() if label.exists() else f.name
                sensors.append({"name": f"{name} {lab}", "source": "hwmon", "temp_c": round(t, 1)})
        return sensors, self._load()


# ---------------------------------------------------------------- one reading, any platform
class Sensors:
    """Reads the machine's sensors. Construct once and keep: Windows rate counters need the previous sample."""

    def __init__(self, linux_root: str = "/"):
        self.kind = "none"
        self.error: Optional[str] = None
        self._pdh: Optional[_Pdh] = None
        self._sys: Optional[_Sysfs] = None
        if os.name == "nt":
            try:
                self._pdh = _Pdh(PDH_PATHS)
                self.kind = "windows-pdh (under Wine)" if self._pdh.wine else "windows-pdh"
            except Exception as e:                        # noqa: BLE001 - reported, never fatal
                self.error = f"{type(e).__name__}: {e}"
        elif sys.platform.startswith("linux"):
            self._sys = _Sysfs(linux_root)
            self.kind = "linux-sysfs"
        self._lock = threading.Lock()

    def missing(self) -> dict[str, str]:
        return dict(self._pdh.missing) if self._pdh else {}

    def read(self) -> dict:
        with self._lock:
            r: dict[str, Any] = {"ts": int(time.time() * 1000), "source": self.kind, "sensors": [], "max_temp_c": None,
                                 "passive_limit_pct": None, "throttle_reasons": None, "cpu_load_pct": None,
                                 "cpu_perf_pct": None, "cpu_mhz": None, "perf_limit_flags": None,
                                 "invalid_readings": [], "error": self.error}
            if self._pdh is not None:
                try:
                    v = self._pdh.read()
                except Exception as e:                    # noqa: BLE001
                    r["error"] = f"{type(e).__name__}: {e}"
                    v = {}
                hp, plain = v.get("zone_temp_hp", {}), v.get("zone_temp", {})
                for name in sorted(set(hp) | set(plain)):
                    k = hp[name] / 10.0 if name in hp else plain[name]
                    r["sensors"].append({"name": name, "source": "ACPI thermal zone", "temp_c": round(k - 273.15, 1)})
                if v.get("zone_passive"):
                    r["passive_limit_pct"] = round(min(v["zone_passive"].values()), 1)
                if v.get("zone_throttle"):
                    r["throttle_reasons"] = int(max(v["zone_throttle"].values()))
                load = v.get("cpu_load") or v.get("cpu_load_basic") or {}
                if load:
                    r["cpu_load_pct"] = round(next(iter(load.values())), 1)
                if v.get("cpu_perf"):
                    r["cpu_perf_pct"] = round(next(iter(v["cpu_perf"].values())), 1)
                if v.get("cpu_mhz"):
                    base = next(iter(v["cpu_mhz"].values()))
                    r["cpu_mhz"] = round(base * (r["cpu_perf_pct"] or 100.0) / 100.0)
                if v.get("cpu_limit"):
                    r["perf_limit_flags"] = int(next(iter(v["cpu_limit"].values())))
            elif self._sys is not None:
                r["sensors"], r["cpu_load_pct"] = self._sys.read()
            lo, hi = SAME_SENSOR_LIMITS
            valid = []
            for s in r["sensors"]:
                (valid if lo <= s["temp_c"] <= hi else r["invalid_readings"]).append(s)
            r["sensors"] = valid
            r["max_temp_c"] = max((s["temp_c"] for s in valid), default=None)
            return r


def assess(r: dict) -> dict:
    """Plain-language status of one reading: ok, warning, critical or unknown (nothing measurable)."""
    reasons, status = [], "ok"
    t = r.get("max_temp_c")
    if t is not None and t >= CRIT_C:
        status = "critical"
        reasons.append(f"temperature {t:.0f} °C: at or above {CRIT_C:.0f} °C")
    elif t is not None and t >= WARN_C:
        status = "warning"
        reasons.append(f"temperature {t:.0f} °C: above {WARN_C:.0f} °C")
    p = r.get("passive_limit_pct")
    if p is not None and p < 100:
        status = "critical" if status == "critical" else "warning"
        reasons.append(f"Windows is slowing the CPU to cool it (passive limit {p:.0f}%)")
    tr = r.get("throttle_reasons")
    if tr:
        status = "critical" if status == "critical" else "warning"
        reasons.append(f"a thermal zone reports throttling (reason code {tr})")
    load, perf = r.get("cpu_load_pct"), r.get("cpu_perf_pct")
    if load is not None and perf is not None and load >= 50 and perf < PERF_LOW_PCT:
        status = "critical" if status == "critical" else "warning"
        reasons.append(f"CPU running at {perf:.0f}% of its normal speed while {load:.0f}% busy")
    measurable = t is not None or p is not None or tr is not None or perf is not None
    if not measurable:
        status = "unknown"
    return {"status": status, "reasons": reasons, "temperature": "measured" if t is not None else "not reported",
            "thermal": status in ("warning", "critical") and any(
                ("temperature" in x or "cool" in x or "throttl" in x) for x in reasons)}


# ---------------------------------------------------------------- the load test
def _load_workers(n: int, stop: threading.Event, counts: list[int]) -> list[threading.Thread]:
    import numpy as np

    def work(i: int) -> None:
        a = np.random.default_rng(i).random(500_000)
        b = np.empty_like(a)
        while not stop.is_set():
            np.sqrt(np.sin(a) * np.cos(a) + 2.0, out=b)    # numpy releases the GIL: one thread keeps one core busy
            counts[i] += 1
    ts = [threading.Thread(target=work, args=(i,), name=f"thermal-load-{i}", daemon=True) for i in range(n)]
    for t in ts:
        t.start()
    return ts


def run_check(sensors: Sensors, minutes: float = 5.0, *, baseline_s: float = 60.0, cooldown_s: float = 60.0,
              sample_s: float = 5.0, threads: Optional[int] = None, stop: Optional[threading.Event] = None,
              progress: Optional[Callable[[dict], None]] = None) -> dict:
    """Baseline (idle) -> full load on every logical CPU -> cool-down, sampling the sensors and the work rate.
    The load stops at once if the temperature reaches CRIT_C. Returns the verdict with every sample."""
    stop = stop or threading.Event()
    n = max(1, threads or os.cpu_count() or 1)
    samples: list[dict] = []
    t0 = time.time()
    aborted = None
    counts = [0] * n
    load_stop = threading.Event()
    workers: list[threading.Thread] = []
    plan = [("baseline", baseline_s), ("load", minutes * 60.0), ("cooldown", cooldown_s)]
    last_count, last_t = 0, time.time()
    for phase, length in plan:
        if stop.is_set() or (aborted and phase == "load"):
            break
        if phase == "load":
            workers = _load_workers(n, load_stop, counts)
            last_count, last_t = 0, time.time()
        if phase == "cooldown":
            load_stop.set()
            for w in workers:
                w.join(timeout=5)
        end = time.time() + length
        while time.time() < end and not stop.is_set():
            stop.wait(min(sample_s, max(0.0, end - time.time())))
            r = sensors.read()
            now, c = time.time(), sum(counts)
            rate = (c - last_count) / max(1e-6, now - last_t) if phase == "load" else None
            last_count, last_t = c, now
            s = {"t_s": round(now - t0, 1), "phase": phase, "max_temp_c": r["max_temp_c"],
                 "passive_limit_pct": r["passive_limit_pct"], "throttle_reasons": r["throttle_reasons"],
                 "cpu_load_pct": r["cpu_load_pct"], "cpu_perf_pct": r["cpu_perf_pct"], "cpu_mhz": r["cpu_mhz"],
                 "perf_limit_flags": r["perf_limit_flags"], "work_rate": None if rate is None else round(rate, 1),
                 "status": assess(r)["status"]}
            samples.append(s)
            if progress:
                progress(s)
            if phase == "load" and r["max_temp_c"] is not None and r["max_temp_c"] >= CRIT_C:
                aborted = f"stopped at {r['max_temp_c']:.0f} °C (limit {CRIT_C:.0f} °C)"
                break
        if aborted and phase == "load":
            load_stop.set()
    load_stop.set()
    for w in workers:
        w.join(timeout=5)
    return summarise(samples, n, aborted, stop.is_set(), minutes, sensors)


def summarise(samples: list[dict], threads: int, aborted: Optional[str], stopped: bool, minutes: float,
              sensors: Optional[Sensors] = None) -> dict:
    def col(phase: str, k: str) -> list:
        return [s[k] for s in samples if s["phase"] == phase and s[k] is not None]
    temps_all = [s["max_temp_c"] for s in samples if s["max_temp_c"] is not None]
    base, load, cool = col("baseline", "max_temp_c"), col("load", "max_temp_c"), col("cooldown", "max_temp_c")
    rates = [s["work_rate"] for s in samples if s["phase"] == "load" and s["work_rate"]]
    early = rates[:max(1, min(6, len(rates) // 4))] if rates else []
    late = rates[-max(1, min(12, len(rates) // 4)):] if rates else []
    drop = None
    if early and late and max(early) > 0:
        drop = round(1 - (sum(late) / len(late)) / (sum(early) / len(early)), 3)
    passive = col("load", "passive_limit_pct")
    throttle = [x for x in col("load", "throttle_reasons") if x]
    perf_load = col("load", "cpu_perf_pct")
    busy_load = col("load", "cpu_load_pct")
    reasons, verdict = [], "PASS"
    measured = bool(temps_all)
    peak = max(load) if load else None
    if aborted:
        verdict = "FAIL"
        reasons.append(f"load {aborted}: the cooling cannot hold full load")
    elif peak is not None and peak >= CRIT_C:
        verdict = "FAIL"
        reasons.append(f"peak {peak:.0f} °C under load (limit {CRIT_C:.0f} °C)")
    if peak is not None and WARN_C <= peak < CRIT_C:
        verdict = "WARNING" if verdict == "PASS" else verdict
        reasons.append(f"peak {peak:.0f} °C under load: above {WARN_C:.0f} °C")
    if passive and min(passive) < 100:
        verdict = "WARNING" if verdict == "PASS" else verdict
        reasons.append(f"Windows slowed the CPU to cool it (passive limit down to {min(passive):.0f}%)")
    if throttle:
        verdict = "WARNING" if verdict == "PASS" else verdict
        reasons.append(f"a thermal zone reported throttling {len(throttle)} time(s)")
    if drop is not None and drop > RATE_DROP_WARN:
        verdict = "WARNING" if verdict == "PASS" else verdict
        reasons.append(f"work rate fell {drop:.0%} from the start to the end of the load (thermal or power limit)")
    if perf_load and min(perf_load) < PERF_LOW_PCT:
        verdict = "WARNING" if verdict == "PASS" else verdict
        reasons.append(f"CPU speed went down to {min(perf_load):.0f}% of normal under load")
    if stopped and verdict == "PASS":
        verdict = "STOPPED"
        reasons.append("stopped before the end: no conclusion")
    if verdict == "PASS":
        if measured:
            reasons.append(f"peak {peak:.0f} °C under full load, no throttling, speed held steady"
                           if peak is not None else "no throttling, speed held steady")
        else:
            verdict = "PASS (no temperature sensor)"
            reasons.append("this PC reports no temperature to the operating system; the CPU kept its speed under full load "
                           "with no throttling reported" if (rates or perf_load) else
                           "nothing measurable was reported")
    return {
        "verdict": verdict, "reasons": reasons, "minutes": minutes, "threads": threads,
        "temperature": "measured" if measured else "not reported by this PC",
        "baseline_c": round(sum(base) / len(base), 1) if base else None, "peak_load_c": peak,
        "end_of_cooldown_c": cool[-1] if cool else None,
        "recovered_c": round(peak - cool[-1], 1) if (peak is not None and cool) else None,
        "work_rate_drop": drop, "min_passive_limit_pct": min(passive) if passive else None,
        "min_perf_pct_under_load": min(perf_load) if perf_load else None,
        "mean_load_pct": round(sum(busy_load) / len(busy_load), 1) if busy_load else None,
        "samples": samples, "machine": machine(),
        "counters_missing": sensors.missing() if sensors else {}, "sensor_source": sensors.kind if sensors else None,
        "aborted": aborted, "stopped": stopped,
        "note": ("A thermal zone reported by Windows is often the motherboard or chipset, not the CPU core itself; "
                 "a dedicated tool such as HWiNFO shows the core temperature. The work-rate figure is measured "
                 "directly and falls if the CPU throttles."),
    }


def report_text(res: dict) -> str:
    m = res["machine"]
    win = m.get("windows") or {}
    change = "-" if res["work_rate_drop"] is None else f"{-res['work_rate_drop']:+.0%}"
    L = ["TRADING AI - THERMAL CHECK", "=" * 60,
         f"Result:  {res['verdict']}"] + [f"  - {x}" for x in res["reasons"]] + [
        "",
        f"Computer: {win.get('name', m['os'])} (build {win.get('build', '-')}), {m.get('cpu') or 'CPU not reported'}, "
        f"{m['logical_cpus']} logical CPUs",
        f"Load:     {res['threads']} threads for {res['minutes']:g} minute(s); average CPU busy "
        f"{res['mean_load_pct'] if res['mean_load_pct'] is not None else 'not reported'}%",
        f"Temperature: {res['temperature']}",
        f"  idle (baseline)   {_c(res['baseline_c'])}",
        f"  peak under load   {_c(res['peak_load_c'])}",
        f"  after cool-down   {_c(res['end_of_cooldown_c'])}",
        f"Work rate change from start to end of load: {change}",
        f"Lowest passive limit (100% = not throttled): {_p(res['min_passive_limit_pct'])}",
        f"Lowest CPU speed under load (100% = normal): {_p(res['min_perf_pct_under_load'])}",
        "", "Samples (seconds, phase, temperature, CPU busy, speed, passive limit, work rate):"]
    for s in res["samples"]:
        L.append(f"  {s['t_s']:7.1f}  {s['phase']:<8} {_c(s['max_temp_c']):>9}  {_p(s['cpu_load_pct']):>6}  "
                 f"{_p(s['cpu_perf_pct']):>6}  {_p(s['passive_limit_pct']):>6}  "
                 f"{'-' if s['work_rate'] is None else s['work_rate']}")
    if res.get("counters_missing"):
        L += ["", "Counters this Windows did not provide: " + ", ".join(sorted(res["counters_missing"]))]
    L += ["", res["note"], "",
          "Thresholds: warning at 85 °C, stop at 95 °C, warning if the work rate falls more than 30% or Windows "
          "limits the CPU.", "This report was produced by measuring this computer; nothing in it is estimated."]
    return "\n".join(L) + "\n"


def _c(x: Optional[float]) -> str:
    return "not reported" if x is None else f"{x:.1f} °C"


def _p(x: Optional[float]) -> str:
    return "-" if x is None else f"{x:.0f}%"


def save_report(res: dict, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = folder / f"thermal-check-{stamp}.txt"
    path.write_text(report_text(res), encoding="utf-8")
    (folder / f"thermal-check-{stamp}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return path


# ---------------------------------------------------------------- inside the running program
class HardwareMonitor:
    """Samples the sensors every 30 seconds while the program runs, warns when the computer runs hot, tells the master
    to pause training (the heaviest work) while it does, and runs the thermal check on request."""

    INTERVAL = 30.0

    def __init__(self, app: "App"):
        self.app = app
        self.sensors = Sensors()
        self.last: Optional[dict] = None
        self.assessment: dict = {"status": "unknown", "reasons": [], "temperature": "not reported", "thermal": False}
        self.history: deque = deque(maxlen=240)
        self.check: dict = {"state": "idle"}
        self._stop = threading.Event()
        self._check_stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._hot_since: Optional[float] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="hardware", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._check_stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.check.get("state") != "running":       # the check samples by itself
                try:
                    self.sample()
                except Exception as e:                    # noqa: BLE001 - reported, never fatal
                    self.app.bus.publish("system.error", {"error": f"hardware: {type(e).__name__}: {e}"},
                                         severity="warning")
            self._stop.wait(self.INTERVAL)

    def sample(self) -> dict:
        r = self.sensors.read()
        a = assess(r)
        prev = self.assessment.get("status")
        with self._lock:
            self.last, self.assessment = r, a
            self.history.append({"ts": r["ts"], "max_temp_c": r["max_temp_c"], "cpu_load_pct": r["cpu_load_pct"],
                                 "cpu_perf_pct": r["cpu_perf_pct"], "passive_limit_pct": r["passive_limit_pct"],
                                 "status": a["status"]})
            self._hot_since = (self._hot_since or time.time()) if a["thermal"] else None
        if a["status"] != prev and a["status"] in ("warning", "critical"):
            msg = "Computer running hot: " + "; ".join(a["reasons"]) + ". Training is paused until it cools down."
            self.app.audit("hardware", msg, severity="warning" if a["status"] == "warning" else "critical",
                           data={"reading": r})
            self.app.bus.publish("hardware", {"status": a["status"], "message": msg, "reasons": a["reasons"]},
                                 severity="warning" if a["status"] == "warning" else "critical")
        elif prev in ("warning", "critical") and a["status"] in ("ok", "unknown"):
            self.app.bus.publish("hardware", {"status": a["status"], "message": "Computer temperature back to normal; "
                                              "training resumes."}, severity="info")
        return r

    def hot(self) -> bool:
        """True while the last reading shows a thermal problem, or while the thermal check is loading the CPU."""
        return bool(self.assessment.get("thermal")) or self.check.get("state") == "running"

    def start_check(self, minutes: float = 5.0) -> dict:
        minutes = max(1.0, min(30.0, float(minutes)))
        with self._lock:
            if self.check.get("state") == "running":
                raise ValueError("a thermal check is already running")
            self._check_stop = threading.Event()
            self.check = {"state": "running", "started": int(time.time() * 1000), "minutes": minutes, "samples": [],
                          "phase": "baseline"}

        def prog(s: dict) -> None:
            self.check["samples"] = (self.check["samples"] + [s])[-400:]
            self.check["phase"] = s["phase"]
            self.history.append({"ts": int(time.time() * 1000), "max_temp_c": s["max_temp_c"],
                                 "cpu_load_pct": s["cpu_load_pct"], "cpu_perf_pct": s["cpu_perf_pct"],
                                 "passive_limit_pct": s["passive_limit_pct"], "status": s["status"]})

        def work() -> None:
            try:
                res = run_check(self.sensors, minutes, stop=self._check_stop, progress=prog)
                path = save_report(res, Path(self.app.paths.base) / "thermal-reports")
                self.check = {"state": "done", "result": {k: v for k, v in res.items() if k != "samples"},
                              "samples": res["samples"], "report": str(path), "finished": int(time.time() * 1000)}
                self.app.audit("hardware", f"thermal check: {res['verdict']} - " + "; ".join(res["reasons"]),
                               severity="info" if res["verdict"].startswith("PASS") else "warning",
                               data={"report": str(path)})
                self.app.bus.publish("hardware", {"status": "check", "message": f"Thermal check finished: "
                                                  f"{res['verdict']}.", "verdict": res["verdict"]},
                                     severity="info" if res["verdict"].startswith("PASS") else "warning")
            except Exception as e:                        # noqa: BLE001
                self.check = {"state": "failed", "error": f"{type(e).__name__}: {e}"}
        threading.Thread(target=work, name="thermal-check", daemon=True).start()
        self.app.audit("hardware", f"thermal check started ({minutes:g} min of full CPU load)")
        return self.view()

    def stop_check(self) -> dict:
        self._check_stop.set()
        return self.view()

    def view(self) -> dict:
        with self._lock:
            return {"reading": self.last, "assessment": self.assessment, "history": list(self.history)[-120:],
                    "check": {k: v for k, v in self.check.items() if k != "samples"} | {
                        "samples": self.check.get("samples", [])[-120:]},
                    "machine": machine(), "source": self.sensors.kind, "counters_missing": self.sensors.missing(),
                    "thresholds": {"warning_c": WARN_C, "stop_c": CRIT_C}}
