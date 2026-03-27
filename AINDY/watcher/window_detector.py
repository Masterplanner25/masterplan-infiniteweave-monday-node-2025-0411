"""
window_detector.py — Cross-platform active window detection.

Contract:
  - get_active_window() NEVER raises — always returns WindowInfo or None
  - WindowInfo.app_name is always a non-empty string when not None
  - WindowInfo.window_title may be empty string
  - WindowInfo.pid is 0 if process resolution fails

Platform strategy:
  - Windows: ctypes.windll.user32 (zero deps)
  - macOS: AppKit.NSWorkspace (pyobjc; falls back to psutil)
  - Linux: xdotool subprocess (falls back to psutil)
  - Fallback: psutil highest-CPU process
"""

import logging
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_SYSTEM = platform.system()  # "Windows", "Darwin", "Linux"


@dataclass
class WindowInfo:
    app_name: str
    window_title: str
    pid: int = 0
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Windows detector
# ---------------------------------------------------------------------------

def _detect_windows() -> Optional[WindowInfo]:
    try:
        import ctypes
        import ctypes.wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        # Window title
        length = user32.GetWindowTextLengthW(hwnd) + 1
        title_buf = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, title_buf, length)
        window_title = title_buf.value.strip()

        # PID
        pid = ctypes.wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_val = pid.value

        # Process name
        app_name = _process_name_windows(kernel32, pid_val)

        if not app_name:
            return None

        return WindowInfo(app_name=app_name, window_title=window_title, pid=pid_val)
    except Exception as exc:
        logger.debug("Windows window detection failed: %s", exc)
        return None


def _process_name_windows(kernel32, pid: int) -> str:
    """Resolve process name from PID using QueryFullProcessImageNameW."""
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        try:
            buf_size = ctypes.wintypes.DWORD(260)
            name_buf = ctypes.create_unicode_buffer(260)
            ok = kernel32.QueryFullProcessImageNameW(handle, 0, name_buf, ctypes.byref(buf_size))
            if ok:
                full_path = name_buf.value
                return os.path.basename(full_path).lower()
        finally:
            kernel32.CloseHandle(handle)
    except Exception as exc:
        logger.debug("Process name resolution failed (pid=%d): %s", pid, exc)
    return ""


# ---------------------------------------------------------------------------
# macOS detector
# ---------------------------------------------------------------------------

def _detect_macos() -> Optional[WindowInfo]:
    try:
        from AppKit import NSWorkspace  # type: ignore[import]
        ws = NSWorkspace.sharedWorkspace()
        app = ws.frontmostApplication()
        if app is None:
            return None
        app_name = str(app.localizedName() or "").strip()
        pid = int(app.processIdentifier())
        if not app_name:
            return None
        window_title = _macos_window_title(pid)
        return WindowInfo(app_name=app_name.lower(), window_title=window_title, pid=pid)
    except ImportError:
        logger.debug("AppKit not available; falling back to psutil for macOS")
        return None
    except Exception as exc:
        logger.debug("macOS window detection failed: %s", exc)
        return None


def _macos_window_title(pid: int) -> str:
    """Best-effort window title via Quartz, silent on failure."""
    try:
        import Quartz  # type: ignore[import]
        window_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        if window_list:
            for w in window_list:
                if w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowLayer") == 0:
                    return str(w.get("kCGWindowName") or "")
    except Exception:
        logger.debug("macOS Quartz window-title lookup failed for pid=%s", pid)
    return ""


# ---------------------------------------------------------------------------
# Linux detector
# ---------------------------------------------------------------------------

def _detect_linux() -> Optional[WindowInfo]:
    try:
        wid = subprocess.check_output(
            ["xdotool", "getactivewindow"],
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).decode().strip()
        if not wid:
            return None

        title = subprocess.check_output(
            ["xdotool", "getwindowname", wid],
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).decode().strip()

        pid_raw = subprocess.check_output(
            ["xdotool", "getwindowpid", wid],
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).decode().strip()
        pid = int(pid_raw) if pid_raw.isdigit() else 0

        app_name = _process_name_psutil(pid) or title.split()[0].lower() if title else ""
        if not app_name:
            return None

        return WindowInfo(app_name=app_name, window_title=title, pid=pid)
    except FileNotFoundError:
        logger.debug("xdotool not found; falling back to psutil for Linux")
        return None
    except Exception as exc:
        logger.debug("Linux window detection failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# psutil fallback
# ---------------------------------------------------------------------------

def _detect_psutil_fallback() -> Optional[WindowInfo]:
    """Return the highest-CPU process as a best-effort proxy for active window."""
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["name", "cpu_percent", "pid"]):
            try:
                info = p.info
                if info.get("cpu_percent", 0) is not None:
                    procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                logger.debug("psutil process skipped during fallback detection: %s", exc)

        if not procs:
            return None

        # Two-pass: first call seeds cpu_percent; second pass needed for accuracy.
        # For our purposes the initial reading is sufficient.
        top = max(procs, key=lambda x: x.get("cpu_percent") or 0.0)
        name = (top.get("name") or "").lower().strip()
        if not name:
            return None
        return WindowInfo(
            app_name=name,
            window_title="",
            pid=top.get("pid", 0),
            extra={"source": "psutil_fallback"},
        )
    except Exception as exc:
        logger.debug("psutil fallback detection failed: %s", exc)
        return None


def _process_name_psutil(pid: int) -> str:
    """Resolve process name for a PID using psutil."""
    if pid <= 0:
        return ""
    try:
        import psutil
        return psutil.Process(pid).name().lower()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_active_window() -> Optional[WindowInfo]:
    """
    Return information about the currently focused window.

    Never raises. Returns None when detection is not possible.
    """
    if _SYSTEM == "Windows":
        result = _detect_windows()
    elif _SYSTEM == "Darwin":
        result = _detect_macos()
    elif _SYSTEM == "Linux":
        result = _detect_linux()
    else:
        result = None

    if result is None:
        result = _detect_psutil_fallback()

    return result
