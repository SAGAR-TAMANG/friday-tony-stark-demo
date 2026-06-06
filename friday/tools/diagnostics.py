"""
Diagnostics tools — FRIDAY's read-out of the host she runs on.

This is the local-machine equivalent of the suit's integrity report and
tactical awareness: live CPU / memory / disk / battery, the heaviest
processes, and what's currently listening on the network. All read-only —
nothing here changes system state.
"""

from __future__ import annotations

import socket
import time
from datetime import datetime, timedelta

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - psutil is a declared dep, guard anyway
    psutil = None


def _need_psutil() -> str | None:
    if psutil is None:
        return "Diagnostics subsystem offline, boss — psutil isn't installed."
    return None


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def register(mcp):

    @mcp.tool()
    def run_diagnostics() -> str:
        """
        Full host integrity report: CPU load, memory, disk, battery, and
        uptime. Use when the boss asks for a system check, diagnostics, or
        'how are we doing'.
        """
        err = _need_psutil()
        if err:
            return err

        lines = ["### SYSTEM DIAGNOSTICS\n"]

        cpu_pct = psutil.cpu_percent(interval=0.3)
        cores = psutil.cpu_count(logical=True)
        lines.append(f"CPU: {cpu_pct:.0f}% across {cores} logical cores")
        try:
            load = psutil.getloadavg()
            lines.append(f"Load avg (1/5/15m): {load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f}")
        except (AttributeError, OSError):
            pass

        vm = psutil.virtual_memory()
        lines.append(
            f"Memory: {_fmt_bytes(vm.used)} / {_fmt_bytes(vm.total)} "
            f"({vm.percent:.0f}% used)"
        )

        try:
            disk = psutil.disk_usage("/")
            lines.append(
                f"Disk (/): {_fmt_bytes(disk.used)} / {_fmt_bytes(disk.total)} "
                f"({disk.percent:.0f}% used)"
            )
        except OSError:
            pass

        battery = getattr(psutil, "sensors_battery", lambda: None)()
        if battery is not None:
            state = "charging" if battery.power_plugged else "on battery"
            lines.append(f"Power: {battery.percent:.0f}% ({state})")

        try:
            boot = datetime.fromtimestamp(psutil.boot_time())
            up = datetime.now() - boot
            lines.append(f"Uptime: {str(timedelta(seconds=int(up.total_seconds())))}")
        except Exception:
            pass

        return "\n".join(lines)

    @mcp.tool()
    def top_processes(sort_by: str = "cpu", limit: int = 8) -> str:
        """
        List the heaviest running processes. sort_by is 'cpu' or 'memory'.
        Use for 'what's hogging the machine' / 'what's slowing me down'.
        """
        err = _need_psutil()
        if err:
            return err

        limit = max(1, min(limit, 30))
        key = "memory" if sort_by.lower().startswith("mem") else "cpu"

        # Prime CPU counters, then sample.
        for p in psutil.process_iter():
            try:
                p.cpu_percent(None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        time.sleep(0.3)

        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_percent"]):
            try:
                cpu = p.cpu_percent(None)
                mem = p.info["memory_percent"] or 0.0
                procs.append((p.info["pid"], p.info["name"] or "?", cpu, mem))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        idx = 2 if key == "cpu" else 3
        procs.sort(key=lambda t: t[idx], reverse=True)

        header = f"### TOP PROCESSES (by {key})\n"
        rows = [header]
        for pid, name, cpu, mem in procs[:limit]:
            rows.append(f"{pid:>7}  {name[:28]:<28} cpu {cpu:5.1f}%  mem {mem:4.1f}%")
        return "\n".join(rows)

    @mcp.tool()
    def network_scan() -> str:
        """
        Show what's listening on this machine plus active connection counts.
        The local 'what's exposed' security read-out. Read-only.
        """
        err = _need_psutil()
        if err:
            return err

        try:
            conns = psutil.net_connections(kind="inet")
        except (psutil.AccessDenied, PermissionError):
            return "Can't read connection table without elevated access, boss."

        listening = []
        established = 0
        for c in conns:
            if c.status == psutil.CONN_LISTEN and c.laddr:
                listening.append((c.laddr.port, c.laddr.ip, c.pid))
            elif c.status == "ESTABLISHED":
                established += 1

        listening = sorted(set(listening))
        host = socket.gethostname()
        lines = [f"### NETWORK STATUS — {host}\n"]
        lines.append(f"Active (ESTABLISHED) connections: {established}")
        lines.append(f"Listening sockets: {len(listening)}\n")
        for port, ip, pid in listening[:25]:
            name = "?"
            if pid:
                try:
                    name = psutil.Process(pid).name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            lines.append(f"  {ip}:{port}  ← {name} (pid {pid or '—'})")
        if len(listening) > 25:
            lines.append(f"  …and {len(listening) - 25} more")
        return "\n".join(lines)
