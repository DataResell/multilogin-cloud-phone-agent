"""Tiny git-ignored runtime state so separate agent tool-calls share one ADB
connection.

Holds the device serial and a *transient* glogin code — never a durable secret,
and never committed. The ``.mlxphone/`` directory is in ``.gitignore``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

STATE_DIR = Path(os.getenv("MLXPHONE_STATE_DIR", ".mlxphone"))
STATE_FILE = STATE_DIR / "device.json"


def save_device(
    phone_id: str,
    serial: str,
    pwd: str,
    adb_bin: str = "adb",
    watchdog_pid: Optional[int] = None,
) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(
            {
                "phone_id": phone_id,
                "serial": serial,
                "pwd": pwd,
                "adb_bin": adb_bin,
                "watchdog_pid": watchdog_pid,
            }
        )
    )
    try:
        os.chmod(STATE_FILE, 0o600)
    except OSError:  # pragma: no cover - best effort
        pass


def load_device() -> Optional[dict]:
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text())
    except (ValueError, OSError):
        return None


def clear_device() -> None:
    try:
        STATE_FILE.unlink()
    except FileNotFoundError:
        pass
