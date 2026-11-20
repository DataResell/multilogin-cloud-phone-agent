"""Regression tests for the cold-start hardening and the device tools.

Runs with pytest (`python -m pytest`) or standalone (`python tests/test_hardening.py`).
No network or device needed.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mlxphone import start_wait, tools  # noqa: E402
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


def test_endpoint_not_found_404_is_unavailable():
    nested = MlxHTTPError("404", status_code=404, body={"status": {"error_code": "ENDPOINT_NOT_FOUND"}})
    flat = MlxHTTPError("404", status_code=404, body={"error_code": "ENDPOINT_NOT_FOUND"})
    assert nested.endpoint_unavailable and flat.endpoint_unavailable


def test_other_404_is_not_unavailable():
    assert not MlxHTTPError("404", status_code=404, body={"status": {"error_code": "PROFILE_NOT_FOUND"}}).endpoint_unavailable
    assert not MlxHTTPError("404", status_code=404, body={}).endpoint_unavailable
    assert not MlxHTTPError("404", status_code=404, body="oops").endpoint_unavailable


def test_remaining_minutes_endpoint_not_found_is_unknown():
    c = MlxClient(token="t")
    err = MlxHTTPError("404", status_code=404, body={"status": {"error_code": "ENDPOINT_NOT_FOUND"}})
    c.get_limit = lambda: (_ for _ in ()).throw(err)
    assert c.remaining_minutes(log=lambda m: None) is None


# ---- device tools (fake adb; no device needed) ---------------------------

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image"


class _FakeDev:
    def __init__(self, shell_out=None):
        self.serial, self.adb_bin = "1.2.3.4:5555", "adb"
        self.shell_calls = []
        self.shell_out = shell_out or {}
        self.glogins = 0

    def glogin(self):
        self.glogins += 1

    def shell(self, *args, timeout=60):
        self.shell_calls.append(args)
        out = next((v for k, v in self.shell_out.items() if args[: len(k)] == k), "")
        return SimpleNamespace(stdout=out, stderr="", returncode=0)


def _patch_run(fake):
    orig = tools.subprocess.run
    tools.subprocess.run = fake
    return orig


def test_screenshot_stream_ok():
    dev = _FakeDev()
    orig = _patch_run(lambda cmd, **kw: SimpleNamespace(stdout=PNG, stderr=b"", returncode=0))
    try:
        assert tools._screencap(dev) == PNG
        assert dev.glogins == 1 and not dev.shell_calls  # no fallback used
    finally:
        tools.subprocess.run = orig


def test_screenshot_falls_back_to_pull_on_timeout():
    dev = _FakeDev()

    def fake_run(cmd, **kw):
        if "exec-out" in cmd:
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
        if "pull" in cmd:
            Path(cmd[-1]).write_bytes(PNG)
            return SimpleNamespace(stdout="1 file pulled", stderr="", returncode=0)
        raise AssertionError(cmd)

    orig = _patch_run(fake_run)
    try:
        assert tools._screencap(dev) == PNG
        assert dev.shell_calls[0][:2] == ("screencap", "-p")
        assert dev.shell_calls[-1][:2] == ("rm", "-f")  # phone copy cleaned up
    finally:
        tools.subprocess.run = orig


def test_screenshot_falls_back_on_non_png():
    dev = _FakeDev()

    def fake_run(cmd, **kw):
        if "exec-out" in cmd:
            return SimpleNamespace(stdout=b"error: closed", stderr=b"", returncode=1)
        Path(cmd[-1]).write_bytes(PNG)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    orig = _patch_run(fake_run)
    try:
        assert tools._screencap(dev) == PNG
    finally:
        tools.subprocess.run = orig


def test_launch_uses_resolved_activity():
    dev = _FakeDev({("cmd", "package"): "priority=0\ncom.instagram.android/com.instagram.mainactivity.LauncherActivity\n"})
    tools.cmd_launch(dev, ["com.instagram.android"])
    assert ("am", "start", "-n", "com.instagram.android/com.instagram.mainactivity.LauncherActivity") in dev.shell_calls
    assert not any(c[0] == "monkey" for c in dev.shell_calls)


def test_launch_falls_back_to_monkey():
    dev = _FakeDev({("cmd", "package"): "No activity found\n", ("monkey",): "Events injected: 1\n"})
    tools.cmd_launch(dev, ["com.example.app"])
    assert dev.shell_calls[-1][0] == "monkey"


def test_launch_rejects_bad_package():
    for bad in ([], ["not a package"], ["com.x; rm -rf /"], ["a", "b"]):
        try:
            tools.cmd_launch(_FakeDev(), bad)
            assert False, f"expected MlxError for {bad}"
        except MlxError:
            pass


def test_launch_not_installed_errors():
    dev = _FakeDev({("cmd", "package"): "No activity found\n", ("monkey",): "** No activities found to run, monkey aborted.\n"})
    try:
        tools.cmd_launch(dev, ["com.missing.app"])
        assert False, "expected MlxError"
    except MlxError as e:
        assert "com.missing.app" in str(e)


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
