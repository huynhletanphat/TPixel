"""
core/platform_detector.py
Phát hiện môi trường chạy: Termux | Linux | Windows
Không import bất kỳ file nào trong project.
Import bởi: benchmarker.py, ai_engine.py, install.py, server.py
"""

import os
import platform
from dataclasses import dataclass

PLATFORM_TERMUX  = "termux"
PLATFORM_LINUX   = "linux"
PLATFORM_WINDOWS = "windows"
PLATFORM_UNKNOWN = "unknown"


@dataclass
class PlatformInfo:
    platform      : str   # termux | linux | windows | unknown
    os_name       : str
    architecture  : str   # x86_64 | aarch64 | arm
    python_version: str
    is_termux     : bool
    is_mobile     : bool  # True nếu ARM
    termux_prefix : str


def detect() -> PlatformInfo:
    arch      = platform.machine()
    py_ver    = platform.python_version()
    os_system = platform.system()

    # Termux báo Linux — phân biệt bằng thư mục đặc trưng
    termux_prefix = "/data/data/com.termux/files/usr"
    is_termux     = os.path.isdir(termux_prefix)

    # Fallback: proot-distro che mất thư mục trên, kiểm tra biến môi trường
    if not is_termux and os.environ.get("PREFIX", "").startswith("/data/data/com.termux"):
        is_termux     = True
        termux_prefix = os.environ.get("PREFIX", termux_prefix)

    if is_termux:
        detected = PLATFORM_TERMUX
    elif os_system == "Linux":
        detected = PLATFORM_LINUX
    elif os_system == "Windows":
        detected = PLATFORM_WINDOWS
    else:
        detected = PLATFORM_UNKNOWN

    is_mobile = arch.startswith("aarch64") or arch.startswith("arm")

    try:
        if os_system == "Linux":
            os_name = platform.freedesktop_os_release().get("PRETTY_NAME", os_system)
        elif os_system == "Windows":
            os_name = platform.version()
        else:
            os_name = os_system
    except Exception:
        os_name = os_system

    return PlatformInfo(
        platform       = detected,
        os_name        = os_name,
        architecture   = arch,
        python_version = py_ver,
        is_termux      = is_termux,
        is_mobile      = is_mobile,
        termux_prefix  = termux_prefix if is_termux else "",
    )


if __name__ == "__main__":
    info = detect()
    print(f"Platform : {info.platform}")
    print(f"OS       : {info.os_name}")
    print(f"Arch     : {info.architecture}")
    print(f"Python   : {info.python_version}")
    print(f"Termux?  : {info.is_termux}")
    print(f"Mobile?  : {info.is_mobile}")
    print(f"Prefix   : {info.termux_prefix or 'N/A'}")
