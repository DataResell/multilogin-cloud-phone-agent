"""Enable ADB via Multilogin, connect, and run authenticated device actions.

The glogin session expires in ~30-60s, so :meth:`AdbDevice.shell` re-authenticates
before every action. The transient glogin code comes from the API at runtime and
is never stored in source.
"""
from __future__ import annotations

import subprocess
import time
from typing import Callable, Optional

from .errors import MlxError
from .mlx_client import ADB_ACTIVE, MlxClient


class AdbDevice:
    """A connected cloud phone, addressed by its ``<ip>:<port>`` adb serial."""

    def __init__(self, serial: str, pwd: str, adb_bin: str = "adb") -> None:
        self.serial = serial      # "<ip>:<port>"
        self.pwd = pwd            # transient glogin code (not a durable secret)
        self.adb_bin = adb_bin

    def _run(self, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.adb_bin, "-s", self.serial, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def glogin(self) -> subprocess.CompletedProcess:
        """Authenticate the current adb shell session (expects 'glogin success')."""
        return self._run("shell", "glogin", self.pwd)

    def shell(self, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
        """Re-authenticate (glogin) then run ``adb -s <dev> shell <args>``."""
        self.glogin()
        return self._run("shell", *args, timeout=timeout)

    def disconnect(self) -> None:
        subprocess.run(
            [self.adb_bin, "disconnect", self.serial], capture_output=True, text=True
        )


def enable_and_connect(
    client: MlxClient,
    phone_id: str,
    *,
    adb_bin: str = "adb",
    timeout: int = 120,
    interval: int = 5,
    log: Callable[[str], None] = print,
) -> AdbDevice:
    """Enable ADB, wait until active, ``adb connect``, and glogin.

    Returns a connected :class:`AdbDevice`. Raises ``MlxError`` on timeout.
    """
    log(f"[adb] enabling ADB for {phone_id}")
    client.adb_set(phone_id, True)

    deadline = time.time() + timeout
    while time.time() < deadline:
        items = ((client.adb_info([phone_id]).get("data") or {}).get("items") or [])
        item = next((i for i in items if i.get("id") == phone_id), items[0] if items else None)
        status = (item or {}).get("status")
        if item and status == ADB_ACTIVE and item.get("ip") and item.get("port"):
            ip, port = item["ip"], str(item["port"])
            pwd = item.get("pwd", "")
            serial = f"{ip}:{port}"
            log(f"[adb] active; connecting to {serial}")
            res = subprocess.run(
                [adb_bin, "connect", serial], capture_output=True, text=True, timeout=30
            )
            if "connected" not in (res.stdout + res.stderr).lower():
                raise MlxError(f"adb connect {serial} failed: {(res.stdout or res.stderr).strip()}")
            dev = AdbDevice(serial, pwd, adb_bin)
            login = dev.glogin()
            if "glogin success" not in (login.stdout + login.stderr).lower():
                log(
                    "[adb] warning: glogin did not confirm success: "
                    f"{(login.stdout or login.stderr).strip()}"
                )
            return dev
        log(f"[adb] status={status or 'pending'}; waiting {interval}s")
        time.sleep(interval)

    raise MlxError(f"ADB did not become active for {phone_id} within {timeout}s")
