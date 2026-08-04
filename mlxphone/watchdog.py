"""Detached safety net: force-stop a phone after a deadline, no matter what.

Spawned by ``session start --max-minutes N``. Even if the driving agent crashes
and never calls stop, this process guarantees the phone is stopped — mobile
minutes are billed. It complements (does not replace) the agent's own stop call;
``session stop`` cancels it.
"""
from __future__ import annotations

import sys
import time

from .mlx_client import MlxClient


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("usage: python -m mlxphone.watchdog <phone_id> <sleep_seconds>", file=sys.stderr)
        return 2
    phone_id, sleep_seconds = argv[0], int(argv[1])
    time.sleep(sleep_seconds)
    try:
        MlxClient().stop(phone_id)
        print(f"[watchdog] force-stopped {phone_id} after {sleep_seconds}s")
    except Exception as exc:  # noqa: BLE001 - best-effort safety net
        print(f"[watchdog] failed to stop {phone_id}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
