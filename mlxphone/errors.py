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
    def endpoint_unavailable(self) -> bool:
        """True when the route is not implemented on this account/API tier:
        HTTP 501, or a non-JSON (usually HTML) error page on a known route."""
        return self.status_code == 501 or self.non_json

    @property
    def credentials_rejected(self) -> bool:
        """True when the server rejected the credentials (bad values / auth)."""
        return self.status_code in (400, 401)
