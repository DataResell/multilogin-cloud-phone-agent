"""Error types for the mlxphone harness."""
from __future__ import annotations

from typing import Any, Optional


class MlxError(Exception):
    """Raised for Multilogin API failures or lifecycle problems."""


class MlxHTTPError(MlxError):
    """An HTTP-level failure from the gateway, carrying structured context so
    callers can react to *why* it failed rather than string-matching messages."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        path: Optional[str] = None,
        body: Any = None,
        non_json: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.path = path
        self.body = body
        self.non_json = non_json

    @property
    def error_code(self) -> Optional[str]:
        """The gateway's machine-readable error code, if the body carries one.

        Accepts both ``{"status": {"error_code": ...}}`` and a top-level
        ``{"error_code": ...}``."""
        if not isinstance(self.body, dict):
            return None
        status = self.body.get("status")
        if isinstance(status, dict) and status.get("error_code"):
            return status["error_code"]
        return self.body.get("error_code")

    @property
    def endpoint_unavailable(self) -> bool:
        """True when the route is not implemented on this account/API tier:
        HTTP 501, a non-JSON (usually HTML) error page on a known route, or a
        JSON 404 whose error_code is ``ENDPOINT_NOT_FOUND``. Any other 404
        (e.g. an unknown profile id) is NOT treated as unavailable."""
        if self.status_code == 501 or self.non_json:
            return True
        return self.status_code == 404 and self.error_code == "ENDPOINT_NOT_FOUND"

    @property
    def credentials_rejected(self) -> bool:
        """True when the server rejected the credentials (bad values / auth)."""
        return self.status_code in (400, 401)
