"""Regression tests for the cold-start hardening.

Runs with pytest (`python -m pytest`) or standalone (`python tests/test_hardening.py`).
No network or device needed.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mlxphone import start_wait  # noqa: E402
from mlxphone.errors import MlxError, MlxHTTPError  # noqa: E402
from mlxphone.mlx_client import MlxClient  # noqa: E402


class _FakeClient:
    def __init__(self, start_seq, status_seq, minutes=None):
        self.start_seq = list(start_seq)
        self.status_seq = list(status_seq)
        self.minutes = minutes
        self.starts = 0

    def remaining_minutes(self, log=None):
        return self.minutes

    def start(self, pid):
        r = self.start_seq[min(self.starts, len(self.start_seq) - 1)]
        self.starts += 1
        return r

    def status(self, pid):
        return self.status_seq.pop(0) if self.status_seq else 0


def test_http_error_flags():
    assert MlxHTTPError("x", status_code=501).endpoint_unavailable
    assert MlxHTTPError("x", status_code=200, non_json=True).endpoint_unavailable
    assert MlxHTTPError("x", status_code=400).credentials_rejected
    assert MlxHTTPError("x", status_code=401).credentials_rejected
    assert not MlxHTTPError("x", status_code=500).credentials_rejected


def test_remaining_minutes_501_is_unknown():
    c = MlxClient(token="t")
    c.get_limit = lambda: (_ for _ in ()).throw(MlxHTTPError("501", status_code=501))
    assert c.remaining_minutes(log=lambda m: None) is None


def test_remaining_minutes_other_error_propagates():
    c = MlxClient(token="t")
    c.get_limit = lambda: (_ for _ in ()).throw(MlxHTTPError("500", status_code=500))
    try:
        c.remaining_minutes()
        assert False, "expected MlxHTTPError"
    except MlxHTTPError:
        pass


def test_remaining_minutes_known_value():
    c = MlxClient(token="t")
    c.get_limit = lambda: {"data": {"remaining_limit": 7}}
    assert c.remaining_minutes() == 7


def test_start_capacity_backs_off_then_succeeds():
    orig = time.sleep
    start_wait.time.sleep = lambda s: None
    try:
        fc = _FakeClient(
            start_seq=[{"data": {"fail_details": [{"code": 47002, "msg": "cap"}]}}, {"data": {"fail_details": []}}],
            status_seq=[1, 0],
        )
        start_wait.start_and_wait(fc, "p", timeout=5, interval=0, retries=3, backoff=0, log=lambda m: None)
        assert fc.starts == 2
    finally:
        start_wait.time.sleep = orig


def test_start_non_transient_fails_fast_with_reason():
    fc = _FakeClient(start_seq=[{"data": {"fail_details": [{"code": 12345, "msg": "bad profile"}]}}], status_seq=[])
    try:
        start_wait.start_and_wait(fc, "p", retries=3, backoff=0, log=lambda m: None)
        assert False, "expected MlxError"
    except MlxError as e:
        assert "12345" in str(e) and fc.starts == 1


def test_known_zero_minutes_hard_stops_before_start():
    fc = _FakeClient(start_seq=[{"data": {"fail_details": []}}], status_seq=[0], minutes=0)
    try:
        start_wait.start_and_wait(fc, "p", log=lambda m: None)
        assert False, "expected MlxError"
    except MlxError as e:
        assert "exhausted" in str(e) and fc.starts == 0


def test_signin_auto_retries_with_md5():
    os.environ["MLX_EMAIL"] = "a@b.com"
    os.environ["MLX_PASSWORD"] = "pw"
    os.environ.pop("MLX_HASH_PASSWORD", None)
    c = MlxClient()
    calls = []

    def fake_post(path, body, auth=True):
        calls.append(body["password"])
        if len(calls) == 1:
            raise MlxHTTPError("400", status_code=400)
        return {"data": {"token": "TOK"}}

    c._post = fake_post
    tok = c.signin()
    assert tok == "TOK" and calls[0] == "pw" and calls[1] == hashlib.md5(b"pw").hexdigest()


if __name__ == "__main__":
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = []
    for fn in funcs:
        try:
            fn()
            print(f"[ ok ] {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] {fn.__name__}: {exc}")
            failed.append(fn.__name__)
    print(f"\n{len(funcs) - len(failed)}/{len(funcs)} passed")
    raise SystemExit(1 if failed else 0)
