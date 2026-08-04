"""Lifecycle orchestrator + the always-stop guarantee.

Steps 1 and 3 of the automation live here and are *deterministic* — they must be
code, never an agent's discretion, because the phone must always be stopped
(mobile minutes are billed).

Two ways to use it:

  * In-process (strongest guarantee)::

        with phone_session(phone_id) as dev:
            ...            # step 2: the agent performs actions on `dev`
        # phone is stopped in a finally, even on exception / Ctrl-C.

  * Agent-orchestrated, as separate shell calls::

        python -m mlxphone.session start --phone <id> --max-minutes 20
        python -m mlxphone.tools screenshot        # step 2 (any agent)
        python -m mlxphone.session stop --phone <id>

    ``--max-minutes`` arms a detached watchdog that force-stops the phone on a
    deadline, so it still stops if the agent crashes between calls.
"""
from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Iterator, Optional

from . import doctor as _doctor
from . import state
from .adb import AdbDevice, enable_and_connect
from .checks import ensure_adb
from .errors import MlxError
from .mlx_client import MlxClient
from .start_wait import start_and_wait


def _log(msg: str) -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------
# In-process context manager (strongest always-stop guarantee)
# --------------------------------------------------------------------------
@contextlib.contextmanager
def phone_session(
    phone_id: str,
    *,
    client: Optional[MlxClient] = None,
    adb_bin: str = "adb",
    start_timeout: int = 600,
    adb_timeout: int = 120,
    log: Callable[[str], None] = _log,
) -> Iterator[AdbDevice]:
    """Start -> wait boot -> enable ADB -> yield connected device -> ALWAYS stop."""
    client = client or MlxClient()
    dev: Optional[AdbDevice] = None
    ensure_adb(adb_bin)  # fail before spending minutes if adb is missing
    try:
        start_and_wait(client, phone_id, timeout=start_timeout, log=log)
        dev = enable_and_connect(client, phone_id, adb_bin=adb_bin, timeout=adb_timeout, log=log)
        yield dev
    finally:
        log("[stop] closing session (always-stop)")
        if dev is not None:
            with contextlib.suppress(Exception):
                dev.disconnect()
        # The stop MUST run and its failure MUST surface — do not suppress it.
        client.stop(phone_id)
        state.clear_device()
        log(f"[stop] phone {phone_id} stopped")


# --------------------------------------------------------------------------
# Agent-orchestrated start / stop (separate processes) + watchdog safety net
# --------------------------------------------------------------------------
def open_session(
    phone_id: str,
    *,
    adb_bin: str = "adb",
    max_minutes: Optional[int] = None,
    start_timeout: int = 600,
    adb_timeout: int = 120,
    log: Callable[[str], None] = _log,
) -> AdbDevice:
    """Start the phone and connect ADB, leaving it running for an agent to drive.

    Persists the connection to ``.mlxphone/device.json`` and, if ``max_minutes``
    is given, arms a detached watchdog that force-stops the phone on a deadline.
    """
    client = MlxClient()
    ensure_adb(adb_bin)  # fail before spending minutes if adb is missing
    start_and_wait(client, phone_id, timeout=start_timeout, log=log)
    dev = enable_and_connect(client, phone_id, adb_bin=adb_bin, timeout=adb_timeout, log=log)
    watchdog_pid = _spawn_watchdog(phone_id, max_minutes * 60, log=log) if max_minutes else None
    state.save_device(phone_id, dev.serial, dev.pwd, adb_bin, watchdog_pid=watchdog_pid)
    return dev


def close_session(
    phone_id: Optional[str] = None,
    *,
    adb_bin: str = "adb",
    log: Callable[[str], None] = _log,
) -> None:
    """Stop the phone (always), cancel the watchdog, and clear state."""
    saved = state.load_device() or {}
    phone_id = phone_id or saved.get("phone_id")
    if not phone_id:
        raise MlxError("No phone_id given and no saved session found")

    pid = saved.get("watchdog_pid")
    if pid:
        with contextlib.suppress(ProcessLookupError, PermissionError, ValueError):
            os.kill(int(pid), 9)

    serial = saved.get("serial")
    if serial:
        with contextlib.suppress(Exception):
            subprocess.run(
                [saved.get("adb_bin", adb_bin), "disconnect", serial],
                capture_output=True,
                text=True,
            )

    MlxClient().stop(phone_id)
    state.clear_device()
    log(f"[stop] phone {phone_id} stopped")


def _spawn_watchdog(phone_id: str, sleep_seconds: int, log: Callable[[str], None] = _log) -> int:
    proc = subprocess.Popen(
        [sys.executable, "-m", "mlxphone.watchdog", phone_id, str(sleep_seconds)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    log(f"[start] watchdog armed: force-stop in {sleep_seconds // 60} min (pid {proc.pid})")
    return proc.pid


# --------------------------------------------------------------------------
# Demo action (neutral): prove the loop end to end
# --------------------------------------------------------------------------
def _demo_actions(dev: AdbDevice, results_dir: str = "results", log: Callable[[str], None] = _log) -> None:
    Path(results_dir).mkdir(parents=True, exist_ok=True)
    size = dev.shell("wm", "size")
    log(f"[demo] screen: {size.stdout.strip() or size.stderr.strip()}")
    raw = subprocess.run(
        [dev.adb_bin, "-s", dev.serial, "exec-out", "screencap", "-p"],
        capture_output=True,
        timeout=60,
    )
    shot = Path(results_dir) / "demo_screenshot.png"
    shot.write_bytes(raw.stdout)
    log(f"[demo] saved {shot} ({len(raw.stdout)} bytes)")


def _dry_run_demo(phone_id: str, log: Callable[[str], None] = _log) -> None:
    """Walk the full state machine with no network and no device — for reading/CI."""
    log(f"[start] minutes remaining: 120 (dry-run)")
    log(f"[start] starting phone {phone_id} (attempt 1/3)")
    log("[start] status=1 (starting); waiting ...")
    log("[start] phone is ready")
    log(f"[adb] enabling ADB for {phone_id}")
    log("[adb] active; connecting to <ADB_IP>:<ADB_PORT>")
    log("[demo] screen: Physical size: 1080x1920")
    log("[demo] saved results/demo_screenshot.png (dry-run, 0 bytes)")
    log("[stop] closing session (always-stop)")
    log(f"[stop] phone {phone_id} stopped")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m mlxphone.session",
        description="Multilogin cloud-phone lifecycle (always-stop).",
    )
    parser.add_argument("--adb-bin", default=os.getenv("MLX_ADB_BIN", "adb"))
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="Validate environment + credentials; spends no mobile minutes.")

    p_demo = sub.add_parser("demo", help="Run the full flow with a neutral demo action, then stop.")
    p_demo.add_argument("--phone", default=os.getenv("MOBILE_PROFILE_ID"))
    p_demo.add_argument("--dry-run", action="store_true", help="No network/device; just walk the flow.")

    p_start = sub.add_parser("start", help="Start + connect ADB and leave running for an agent.")
    p_start.add_argument("--phone", default=os.getenv("MOBILE_PROFILE_ID"))
    p_start.add_argument("--max-minutes", type=int, default=None, help="Arm a force-stop watchdog.")

    p_stop = sub.add_parser("stop", help="Always-stop the phone and clear state.")
    p_stop.add_argument("--phone", default=None)

    args = parser.parse_args(argv)

    try:
        if args.cmd == "doctor":
            return _doctor.doctor(adb_bin=args.adb_bin)

        if args.cmd == "demo":
            if not args.phone:
                raise MlxError("Set MOBILE_PROFILE_ID or pass --phone <id>")
            if args.dry_run:
                _dry_run_demo(args.phone)
                return 0
            with phone_session(args.phone, adb_bin=args.adb_bin) as dev:
                _demo_actions(dev)
            return 0

        if args.cmd == "start":
            if not args.phone:
                raise MlxError("Set MOBILE_PROFILE_ID or pass --phone <id>")
            dev = open_session(args.phone, adb_bin=args.adb_bin, max_minutes=args.max_minutes)
            print(f"connected: {dev.serial}")
            return 0

        if args.cmd == "stop":
            close_session(args.phone, adb_bin=args.adb_bin)
            return 0
    except MlxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
