"""Small environment checks shared by the preflight/doctor command and the
lifecycle harness — kept dependency-free so they can run before anything else.
"""
from __future__ import annotations

import platform
import shutil
from typing import Optional

from .errors import MlxError

# Values shipped in .env.example that must be replaced before the tool works.
PLACEHOLDER_VALUES = {"your@email.com", "your-password", "your-token"}


def is_placeholder(value: Optional[str]) -> bool:
    """True for empty / unset values and obvious .env.example placeholders."""
    if value is None:
        return True
    v = value.strip()
    if not v:
        return True
    if v in PLACEHOLDER_VALUES:
        return True
    if v.startswith("<") and v.endswith(">"):  # e.g. <MOBILE_PROFILE_ID>
        return True
    return False


def adb_path(adb_bin: str = "adb") -> Optional[str]:
    return shutil.which(adb_bin)


def adb_install_hint(adb_bin: str = "adb") -> str:
    system = platform.system()
    if system == "Darwin":
        return f"'{adb_bin}' not found on PATH. Install it: brew install android-platform-tools"
    if system == "Linux":
        return (
            f"'{adb_bin}' not found on PATH. Install Android platform-tools "
            "(e.g. `sudo apt install android-tools-adb`) or from "
            "https://developer.android.com/tools/releases/platform-tools"
        )
    return (
        f"'{adb_bin}' not found on PATH. Install Android platform-tools: "
        "https://developer.android.com/tools/releases/platform-tools"
    )


def ensure_adb(adb_bin: str = "adb") -> str:
    """Return the resolved adb path or raise MlxError with a per-OS install hint."""
    path = adb_path(adb_bin)
    if not path:
        raise MlxError(adb_install_hint(adb_bin))
    return path
