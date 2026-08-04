"""`python -m mlxphone.session doctor` — validate the environment and credentials
before spending any mobile minutes.

Runs every check, prints pass/fail + a fix hint for each, and never starts a
phone. Exit code 0 iff all checks pass.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

from . import checks
from .errors import MlxError, MlxHTTPError
from .mlx_client import MlxClient

OK = "[ ok ]"
FAIL = "[FAIL]"


def _print(ok: bool, label: str, detail: str = "") -> None:
    mark = OK if ok else FAIL
    line = f"{mark} {label}"
    if detail:
        line += f" — {detail}"
    print(line)


def check_deps() -> bool:
    try:
        import requests  # noqa: F401
        import dotenv  # noqa: F401
    except Exception as exc:  # pragma: no cover - only if deps missing
        _print(False, "dependencies", f"{exc}. Run: make setup (or python -m pip install -r requirements.txt)")
        return False
    _print(True, "dependencies", "requests, python-dotenv importable")
    return True


def check_adb(adb_bin: str) -> bool:
    path = checks.adb_path(adb_bin)
    if path:
        _print(True, "adb", path)
        return True
    _print(False, "adb", checks.adb_install_hint(adb_bin))
    return False


def check_env() -> bool:
    if not Path(".env").exists():
        _print(False, ".env", "not found. Run: cp .env.example .env  then fill in real values")
        return False
    token = os.getenv("MLX_TOKEN")
    email = os.getenv("MLX_EMAIL")
    password = os.getenv("MLX_PASSWORD")
    profile = os.getenv("MOBILE_PROFILE_ID")

    problems = []
    if checks.is_placeholder(token):
        if checks.is_placeholder(email):
            problems.append("MLX_EMAIL")
        if checks.is_placeholder(password):
            problems.append("MLX_PASSWORD")
    if checks.is_placeholder(profile):
        problems.append("MOBILE_PROFILE_ID")

    if problems:
        _print(False, ".env values", f"still placeholder / empty: {', '.join(problems)} — fill in real values in .env")
        return False
    _print(True, ".env values", "credentials + MOBILE_PROFILE_ID look real")
    return True


def check_signin(client: MlxClient) -> bool:
    if not checks.is_placeholder(os.getenv("MLX_TOKEN")):
        _print(True, "auth", "using MLX_TOKEN (verified by the profile check below)")
        return True
    try:
        client.signin()
    except MlxError as exc:
        _print(False, "auth", str(exc))
        return False
    _print(True, "auth", "sign-in succeeded")
    return True


def check_profile(client: MlxClient) -> bool:
    profile = os.getenv("MOBILE_PROFILE_ID")
    if checks.is_placeholder(profile):
        _print(False, "profile", "MOBILE_PROFILE_ID not set")
        return False
    try:
        resp = client.statuses([profile])
    except MlxHTTPError as exc:
        if exc.credentials_rejected:
            _print(False, "profile", f"auth rejected (HTTP {exc.status_code}); fix credentials first")
        else:
            _print(False, "profile", str(exc))
        return False
    except MlxError as exc:
        _print(False, "profile", str(exc))
        return False

    data = resp.get("data") or {}
    ok_ids = {d.get("id") or d.get("serial_name") for d in (data.get("success_details") or [])}
    # Some tiers key success_details by serial rather than id; also accept a
    # single-item success list as "visible".
    visible = profile in ok_ids or len(data.get("success_details") or []) == 1
    if visible:
        status = (data.get("success_details") or [{}])[0].get("status")
        _print(True, "profile", f"visible (status={status}) — not started")
        return True

    fails = data.get("fail_details") or []
    reason = fails[0].get("msg") if fails else "profile id not found in this workspace"
    _print(False, "profile", f"{reason}. Check MOBILE_PROFILE_ID in the Multilogin desktop app")
    return False


def doctor(adb_bin: str = "adb") -> int:
    print("mlxphone doctor — checking environment (no phone started, no minutes spent)\n")
    results: list[bool] = []

    results.append(check_deps())
    results.append(check_adb(adb_bin))
    env_ok = check_env()
    results.append(env_ok)

    # Only attempt network checks once the local env looks sane.
    client = MlxClient()
    if env_ok:
        signin_ok = check_signin(client)
        results.append(signin_ok)
        if signin_ok:
            results.append(check_profile(client))
        else:
            _print(False, "profile", "skipped (auth failed)")
            results.append(False)
    else:
        _print(False, "auth", "skipped (.env not ready)")
        _print(False, "profile", "skipped (.env not ready)")
        results.extend([False, False])

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} checks passed.")
    if passed == total:
        print("Ready. Try:  make dry-run   then   make demo")
        return 0
    print("Fix the [FAIL] items above, then re-run: make doctor")
    return 1
