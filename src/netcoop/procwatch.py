"""Parent-process watchdog for launcher-managed children.

If the launcher is killed hard (no chance to stop its children), each child notices
that NETCOOP_PARENT_PID is gone and exits, so no orphaned agent/web processes keep
ports busy. Windows uses OpenProcess/GetExitCodeProcess (os.kill(pid, 0) would send
CTRL_C_EVENT there); POSIX uses os.kill(pid, 0).
"""

from __future__ import annotations

import os
import threading
import time

STILL_ACTIVE = 259


def parent_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = k32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start_parent_watchdog(interval_s: float = 2.0) -> None:
    raw = os.environ.get("NETCOOP_PARENT_PID")
    if not raw or not raw.isdigit():
        return
    pid = int(raw)

    def watch():
        while True:
            time.sleep(interval_s)
            if not parent_alive(pid):
                os._exit(3)  # parent launcher is gone: exit instead of lingering as an orphan

    threading.Thread(target=watch, name="parent-watchdog", daemon=True).start()
