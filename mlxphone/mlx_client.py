"""Thin Multilogin gateway API client — the deterministic side of the harness.

Only the HTTPS calls need a Bearer token, obtained cleanly via ``/user/signin``.
The ``adb`` binary authenticates separately (glogin, handled in ``mlxphone.adb``).

No secrets are hardcoded. Credentials are read from the environment / a
git-ignored ``.env`` (see ``.env.example``). Response/status shapes are
documented in ``docs/api-responses.md``.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Callable, Optional

import requests

from .errors import MlxError, MlxHTTPError

try:  # python-dotenv is optional; the toolkit works with plain env vars too.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is a convenience only
    pass

DEFAULT_BASE_URL = "https://api.multilogin.com"

# Phone status codes (Multilogin cloud-phone API contract). See docs/api-responses.md.
STATUS_READY = 0      # running / booted / ready for ADB
STATUS_STARTING = 1   # still booting / proxy session initializing (~20-120s)
STATUS_SHUTDOWN = 2   # shut down
STATUS_EXPIRED = 3    # expired

# adb_status / adb-info item status values.
ADB_ACTIVE = "active"
ADB_DISABLED = "disabled"
ADB_ERROR = "error"


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _short(data: Any, limit: int = 300) -> str:
    text = data if isinstance(data, str) else repr(data)
    return text if len(text) <= limit else text[:limit] + "…"


class MlxClient:
    """Minimal client for the Multilogin cloud-phone gateway endpoints."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = (base_url or os.getenv("MLX_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.token = token or os.getenv("MLX_TOKEN") or None
        self.timeout = timeout
        self._http = requests.Session()

    # ---- auth ------------------------------------------------------------
    def signin(self, email: Optional[str] = None, password: Optional[str] = None) -> str:
        """Sign in and cache a Bearer token. Returns the token.

        Some Multilogin API tiers require the password plaintext, others require
        it MD5-hashed. Unless ``MLX_HASH_PASSWORD=1`` forces the hashed form, this
        tries plaintext first and, on a credentials rejection (HTTP 400 or 401),
        automatically retries once with the MD5 hash — so no manual discovery is
        needed. It logs which form worked.
        """
        email = email or os.getenv("MLX_EMAIL")
        password = password or os.getenv("MLX_PASSWORD")
        if not email or not password:
            raise MlxError(
                "Provide MLX_TOKEN, or MLX_EMAIL + MLX_PASSWORD, in your environment / .env"
            )

        force_hash = os.getenv("MLX_HASH_PASSWORD") == "1"
        attempts = (
            [("MD5-hashed", _md5(password))]
            if force_hash
            else [("plaintext", password), ("MD5-hashed", _md5(password))]
        )

        last_exc: Optional[MlxHTTPError] = None
        for index, (form, pw) in enumerate(attempts):
            try:
                payload = self._post("/user/signin", {"email": email, "password": pw}, auth=False)
            except MlxHTTPError as exc:
                last_exc = exc
                if exc.credentials_rejected and index < len(attempts) - 1:
                    continue  # e.g. plaintext rejected -> try the MD5-hashed form
                raise MlxError(
                    f"Sign-in failed: HTTP {exc.status_code}. Verify MLX_EMAIL / MLX_PASSWORD in .env. "
                    f"(Tried {' then '.join(a[0] for a in attempts)} password; "
                    f"set MLX_HASH_PASSWORD=1 to force the hashed form.)"
                ) from exc

            token = (payload.get("data") or {}).get("token")
            if not token:
                raise MlxError(f"Sign-in returned no token: {payload.get('status')}")
            self.token = token
            if form == "MD5-hashed" and not force_hash:
                print(
                    "[auth] signed in with an MD5-hashed password "
                    "(set MLX_HASH_PASSWORD=1 to skip the plaintext attempt next time)"
                )
            return token

        raise MlxError("Sign-in failed") from last_exc  # pragma: no cover

    def _auth_header(self) -> dict[str, str]:
        if not self.token:
            self.signin()
        return {"Authorization": f"Bearer {self.token}"}

    # ---- low-level -------------------------------------------------------
    def _post(self, path: str, body: dict, auth: bool = True) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if auth:
            headers.update(self._auth_header())
        resp = self._http.post(
            f"{self.base_url}{path}", json=body, headers=headers, timeout=self.timeout
        )
        try:
            data = resp.json()
        except ValueError:
            # Non-JSON (usually an HTML error page) — the route is unavailable on
            # this account / API version. Flag it structurally, don't dump HTML.
            raise MlxHTTPError(
                f"POST {path} -> HTTP {resp.status_code}: non-JSON response "
                f"(endpoint unavailable on this account/API tier)",
                status_code=resp.status_code,
                path=path,
                body=resp.text[:500],
                non_json=True,
            )
        if resp.status_code >= 400:
            raise MlxHTTPError(
                f"POST {path} -> HTTP {resp.status_code}: {_short(data)}",
                status_code=resp.status_code,
                path=path,
                body=data,
            )
        return data

    # ---- lifecycle (all POST, gateway) -----------------------------------
    def get_limit(self) -> dict:
        return self._post("/mobile_profiles/limit", {})

    def remaining_minutes(self, log: Optional[Callable[[str], None]] = None) -> Optional[int]:
        """Remaining mobile minutes, or ``None`` when the metric is unavailable.

        The ``/mobile_profiles/limit`` endpoint is not implemented on every
        account tier (it can return HTTP 501, an HTML page, or a JSON 404 with
        ``error_code: ENDPOINT_NOT_FOUND``). In that case we
        return ``None`` ("unknown") so the caller proceeds — the always-stop
        guarantee + watchdog are the real billing cap. Any *other* error still
        propagates. Returns 0/positive when the metric is actually known.
        """
        try:
            data = self.get_limit().get("data") or {}
        except MlxHTTPError as exc:
            if exc.endpoint_unavailable:
                if log:
                    log(
                        "[start] minutes endpoint unavailable on this tier; proceeding "
                        "(watchdog + always-stop are the billing cap)"
                    )
                return None
            raise
        return data.get("remaining_limit")

    def start(self, phone_id: str) -> dict:
        # Cloud phones run server-side, so starting one is a pure API call — no
        # local launcher (or xcli) is required. The response can be HTTP 200 yet
        # carry data.fail_details (e.g. capacity code 47002); start_and_wait()
        # inspects that. A transient 501 is retried there too.
        return self._post("/mobile_profiles/phone/start", {"ids": [phone_id]})

    def statuses(self, phone_ids: list[str]) -> dict:
        return self._post("/mobile_profiles/phone/statuses", {"ids": phone_ids})

    def status(self, phone_id: str) -> Optional[int]:
        details = ((self.statuses([phone_id]).get("data") or {}).get("success_details") or [])
        return details[0].get("status") if details else None

    def adb_set(self, phone_id: str, enabled: bool = True) -> dict:
        return self._post(
            "/mobile_profiles/phone/adb/set", {"ids": [phone_id], "enabled": enabled}
        )

    def adb_info(self, phone_ids: list[str]) -> dict:
        return self._post("/mobile_profiles/phone/adb/info", {"ids": phone_ids})

    def stop(self, phone_id: str) -> dict:
        return self._post("/mobile_profiles/phone/stop", {"ids": [phone_id]})
