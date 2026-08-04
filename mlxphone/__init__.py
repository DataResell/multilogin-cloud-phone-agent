"""mlxphone — an agent-agnostic toolkit for automating a Multilogin cloud phone.

Two layers:
  * a deterministic lifecycle harness (start -> wait boot -> enable ADB ->
    connect -> ALWAYS stop), and
  * shell/import-callable device tools an AI agent uses to perform the actions.

No credentials are hardcoded anywhere; everything sensitive comes from the
environment (see .env.example) and lives only in a git-ignored .env.
"""
from __future__ import annotations

# Keep stdout/stderr clean for agents parsing tool output. On macOS system Python
# (LibreSSL) urllib3 v2 emits a NotOpenSSLWarning on import; we pin urllib3<2 in
# requirements, and suppress the warning defensively for any environment that
# still has v2. The message filter is set before urllib3 is imported so it also
# covers the import below.
import warnings as _warnings

_warnings.filterwarnings("ignore", message=r"urllib3 v2 only supports OpenSSL")
try:  # pragma: no cover - only present on urllib3 v2
    from urllib3.exceptions import NotOpenSSLWarning as _NotOpenSSLWarning

    _warnings.filterwarnings("ignore", category=_NotOpenSSLWarning)
except Exception:
    pass

from .errors import MlxError, MlxHTTPError
from .mlx_client import (
    MlxClient,
    STATUS_READY,
    STATUS_STARTING,
    STATUS_SHUTDOWN,
    STATUS_EXPIRED,
)

# `phone_session` is imported lazily: importing it eagerly here would pull in
# `mlxphone.session` before `python -m mlxphone.session` can run it as __main__,
# which triggers a RuntimeWarning.
def __getattr__(name: str):  # noqa: D401 - module-level lazy attribute
    if name == "phone_session":
        from .session import phone_session

        return phone_session
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "MlxError",
    "MlxHTTPError",
    "MlxClient",
    "STATUS_READY",
    "STATUS_STARTING",
    "STATUS_SHUTDOWN",
    "STATUS_EXPIRED",
    "phone_session",
]

__version__ = "0.1.0"
