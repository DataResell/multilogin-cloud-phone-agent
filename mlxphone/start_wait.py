"""Deterministic 'start the phone and wait until it has booted' step.

Handles the two ways a start can go wrong beyond a plain error:
  * HTTP 200 with ``data.fail_details`` (server refused the start), and
  * a start that is accepted but never reaches READY.

Both surface a specific cause, never a bare timeout. See docs/api-responses.md.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from .errors import MlxError
from .mlx_client import MlxClient, STATUS_READY, STATUS_SHUTDOWN

# Known start() fail_details codes.
# 47002 = intermittent server-side capacity for the chosen phone version
#         ("Too many requests for your selected phone version…"). Back off & retry.
CAPACITY_CODES = {47002}


def _first_fail(resp: dict) -> Optional[dict]:
    fails = (resp.get("data") or {}).get("fail_details") or []
    return fails[0] if fails else None


def start_and_wait(
    client: MlxClient,
    phone_id: str,
    *,
    timeout: int = 600,
    interval: int = 20,
    retries: int = 3,
    backoff: int = 30,
    log: Callable[[str], None] = print,
) -> None:
    """Preflight minutes, start the phone, and poll until status == READY (0).

    Raises ``MlxError`` with a specific cause if minutes are known-exhausted, the
    server refuses the start (``fail_details``), or the phone never boots.
    """
    remaining = client.remaining_minutes(log=log)
    if remaining is not None and remaining <= 0:
        raise MlxError("Multilogin mobile-profile minutes exhausted; not starting the phone")
    log(f"[start] minutes remaining: {remaining if remaining is not None else 'unknown'}")

    last_fail: Optional[dict] = None
    for attempt in range(1, retries + 1):
        log(f"[start] starting phone {phone_id} (attempt {attempt}/{retries})")
        fail = _first_fail(client.start(phone_id))
        if fail:
            last_fail = fail
            code, msg = fail.get("code"), (fail.get("msg") or "").strip()
            if code in CAPACITY_CODES:
                log(f"[start] server capacity (code {code}): {msg}")
                if attempt < retries:
                    log(f"[start] backing off {backoff}s before retry")
                    time.sleep(backoff)
                    continue
                raise MlxError(
                    f"Phone start refused by server (code {code}): {msg} "
                    "This is intermittent server-side capacity — try again later, or change the "
                    "phone version for this profile in the Multilogin desktop app."
                )
            # Unknown / non-transient refusal: fail fast with the reason.
            raise MlxError(
                f"Phone start refused by server (code {code}): {msg} "
                "Check the mobile profile in the Multilogin desktop app."
            )

        # Start accepted — poll for boot.
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = client.status(phone_id)
            if st == STATUS_READY:
                log("[start] phone is ready")
                return
            if st == STATUS_SHUTDOWN:
                log("[start] phone fell back to shut down; will retry")
                break
            log(f"[start] status={st} (starting); waiting {interval}s")
            time.sleep(interval)

    detail = ""
    if last_fail:
        detail = f" Last server message: {(last_fail.get('msg') or '').strip()} (code {last_fail.get('code')})."
    raise MlxError(
        f"Phone {phone_id} did not reach ready state within {timeout}s x {retries} attempts.{detail}"
    )
