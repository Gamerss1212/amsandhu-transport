"""What this computer actually has, measured, never assumed. Jarvus runs research on the CPU cores of the machine
it is on; it uses no GPU and no remote compute, and says so."""

from __future__ import annotations

import os
import platform
import sys
import time
from typing import Optional


def memory() -> dict:
    total = avail = None
    try:
        with open("/proc/meminfo") as fh:
            d = {ln.split(":")[0]: int(ln.split()[1]) * 1024 for ln in fh if ":" in ln}
        total, avail = d.get("MemTotal"), d.get("MemAvailable")
    except OSError:
        pass
    if total is None and sys.platform == "win32":
        try:
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                total, avail = m.ullTotalPhys, m.ullAvailPhys
        except Exception:                                               # noqa: BLE001
            pass
    return {"total_mb": round(total / 2 ** 20) if total else None, "available_mb": round(avail / 2 ** 20) if avail else None}


def process_rss_mb(pid: Optional[int] = None) -> Optional[float]:
    pid = pid or os.getpid()
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            h = ctypes.windll.kernel32.OpenProcess(0x0410, False, pid)          # QUERY_INFORMATION | VM_READ
            if not h:
                return None
            try:
                pmc = PMC()
                pmc.cb = ctypes.sizeof(PMC)
                if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
                    return pmc.WorkingSetSize / 2 ** 20
            finally:
                ctypes.windll.kernel32.CloseHandle(h)
        except Exception:                                               # noqa: BLE001
            pass
    return None


_cpu_prev = None


def cpu_percent() -> Optional[float]:
    """Whole-machine CPU use since the previous call (Linux /proc/stat; Windows GetSystemTimes)."""
    global _cpu_prev
    cur = None
    try:
        with open("/proc/stat") as fh:
            parts = [int(x) for x in fh.readline().split()[1:]]
        idle, total = parts[3] + (parts[4] if len(parts) > 4 else 0), sum(parts)
        cur = (idle, total)
    except OSError:
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                i, k, u = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
                if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u)):
                    f = lambda ft: (ft.dwHighDateTime << 32) | ft.dwLowDateTime            # noqa: E731
                    cur = (f(i), f(k) + f(u))
            except Exception:                                           # noqa: BLE001
                pass
    if cur is None:
        return None
    prev, _cpu_prev = _cpu_prev, cur
    if prev is None or cur[1] == prev[1]:
        return None
    return round(100.0 * (1 - (cur[0] - prev[0]) / (cur[1] - prev[1])), 1)


def describe(workers: int = None) -> dict:
    mem = memory()
    return {"cpu_logical_cores": os.cpu_count(), "machine": platform.machine(), "os": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(), "memory_total_mb": mem["total_mb"], "memory_available_mb": mem["available_mb"],
            "research_workers": workers, "gpu": None, "remote_compute": None,
            "note": "research runs on this computer's CPU cores; no GPU and no remote or cloud compute is used",
            "measured": int(time.time() * 1000)}
