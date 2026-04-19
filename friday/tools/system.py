"""
System tools — time, host info, CPU/RAM/battery diagnostics.
Requires psutil (listed in pyproject.toml dependencies).
"""

import datetime
import platform

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False


def register(mcp):

    @mcp.tool()
    def get_current_time() -> str:
        """Return the current date and time in ISO 8601 format."""
        return datetime.datetime.now().isoformat()

    @mcp.tool()
    def get_system_info() -> dict:
        """Return basic information about the host system."""
        return {
            "os": platform.system(),
            "os_version": platform.version(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
        }

    @mcp.tool()
    def get_system_diagnostics() -> dict:
        """
        Return live CPU usage, RAM usage, and battery status.
        Use when the boss asks about system health, performance, or power.
        """
        if not _PSUTIL:
            return {"error": "psutil not installed — run `pip install psutil`"}

        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.5)
        battery = psutil.sensors_battery()

        result = {
            "cpu_percent": cpu,
            "ram_used_gb": round(mem.used / 1e9, 2),
            "ram_total_gb": round(mem.total / 1e9, 2),
            "ram_percent": mem.percent,
        }

        if battery:
            result["battery_percent"] = battery.percent
            result["battery_plugged_in"] = battery.power_plugged

        return result
