"""Agent-facing device tools — the step-2 primitives any agent calls over a shell.

    python -m mlxphone.tools screenshot [out.png]
    python -m mlxphone.tools dump-ui   [out.xml]
    python -m mlxphone.tools find      <keyword>
    python -m mlxphone.tools tap       <x> <y>
    python -m mlxphone.tools text      "<string>"
    python -m mlxphone.tools launch    <package>
    python -m mlxphone.tools shell     <args...>

The connected device (serial + transient glogin code) is read from
``.mlxphone/device.json``, written by ``session start``. glogin is refreshed
before every action (the session expires in ~30-60s).

``screenshot`` streams the image first and, if that times out or returns
something that is not a PNG, falls back to saving it on the phone and copying
it with ``adb pull`` (more reliable on busy screens / slow links).
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional

from . import state
from .adb import AdbDevice
from .errors import MlxError

_FIELD_RE = re.compile(r'(text|content-desc|resource-id|bounds)="([^"]*)"')
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
_REMOTE_SHOT = "/sdcard/mlxphone_screen.png"

# Overridable in tests.
STREAM_TIMEOUT = 30
PULL_TIMEOUT = 60


def _device() -> AdbDevice:
    saved = state.load_device()
    if not saved:
        raise MlxError(
            "No connected device. Run: python -m mlxphone.session start --phone <id>"
        )
    return AdbDevice(saved["serial"], saved.get("pwd", ""), saved.get("adb_bin", "adb"))


def _screencap_stream(dev: AdbDevice) -> Optional[bytes]:
    """Fast path: stream the PNG over ``exec-out``. None on timeout / bad data."""
    dev.glogin()
    try:
        data = subprocess.run(
            [dev.adb_bin, "-s", dev.serial, "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=STREAM_TIMEOUT,
        ).stdout
    except subprocess.TimeoutExpired:
        return None
    return data if data.startswith(_PNG_MAGIC) else None


def _screencap_pull(dev: AdbDevice) -> bytes:
    """Fallback: save the PNG on the phone, ``adb pull`` it, delete the copy."""
    try:
        dev.shell("screencap", "-p", _REMOTE_SHOT, timeout=PULL_TIMEOUT)
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "screen.png"
            res = subprocess.run(
                [dev.adb_bin, "-s", dev.serial, "pull", _REMOTE_SHOT, str(local)],
                capture_output=True,
                text=True,
                timeout=PULL_TIMEOUT,
            )
            if res.returncode != 0 or not local.exists():
                raise MlxError(f"adb pull failed: {(res.stderr or res.stdout).strip()}")
            data = local.read_bytes()
    except subprocess.TimeoutExpired as exc:
        raise MlxError(f"screenshot timed out ({exc.timeout}s) on both methods") from exc
    finally:
        try:
            dev.shell("rm", "-f", _REMOTE_SHOT, timeout=15)
        except Exception:  # noqa: BLE001 - cleanup is best-effort
            pass
    if not data.startswith(_PNG_MAGIC):
        raise MlxError("screenshot fallback did not return a PNG image")
    return data


def _screencap(dev: AdbDevice) -> bytes:
    data = _screencap_stream(dev)
    if data is not None:
        return data
    print("[screenshot] streaming failed; falling back to save-and-pull", file=sys.stderr)
    return _screencap_pull(dev)


def _dump_xml(dev: AdbDevice) -> str:
    dev.shell("uiautomator", "dump", "/sdcard/u.xml")
    return dev.shell("cat", "/sdcard/u.xml").stdout


def cmd_screenshot(dev: AdbDevice, args: list[str]) -> None:
    out = Path(args[0]) if args else Path("results/screenshot.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(_screencap(dev))
    print(out)


def cmd_dump_ui(dev: AdbDevice, args: list[str]) -> None:
    out = Path(args[0]) if args else Path("results/ui.xml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_dump_xml(dev))
    print(out)


def cmd_find(dev: AdbDevice, args: list[str]) -> None:
    if not args:
        raise MlxError("usage: find <keyword>")
    keyword = args[0].lower()
    for node in _dump_xml(dev).split("><"):
        if keyword in node.lower():
            fields = [f"{k}={v!r}" for k, v in _FIELD_RE.findall(node) if v]
            if fields:
                print("  ".join(fields))


def cmd_tap(dev: AdbDevice, args: list[str]) -> None:
    if len(args) < 2:
        raise MlxError("usage: tap <x> <y>")
    dev.shell("input", "tap", str(args[0]), str(args[1]))
    print(f"tapped {args[0]},{args[1]}")


def cmd_text(dev: AdbDevice, args: list[str]) -> None:
    if not args:
        raise MlxError("usage: text \"<string>\"")
    # adb `input text` uses %s for spaces; avoid shell-control symbols in captions.
    dev.shell("input", "text", args[0].replace(" ", "%s"))
    print("typed")


def cmd_launch(dev: AdbDevice, args: list[str]) -> None:
    """Open an app's main screen by package name.

    Resolves the launcher activity and starts it with ``am start -n`` (what
    works reliably on cloud phones); falls back to ``monkey`` if resolving fails.
    """
    if len(args) != 1 or not _PACKAGE_RE.match(args[0]):
        raise MlxError("usage: launch <package>   e.g. launch com.instagram.android")
    pkg = args[0]
    res = dev.shell("cmd", "package", "resolve-activity", "--brief",
                    "-c", "android.intent.category.LAUNCHER", pkg)
    component = next(
        (ln.strip() for ln in reversed(res.stdout.splitlines()) if "/" in ln), None
    )
    if component:
        out = dev.shell("am", "start", "-n", component)
        text = out.stdout + out.stderr
        if "Error" not in text and "does not exist" not in text:
            print(f"launched {component}")
            return
    out = dev.shell("monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")
    text = out.stdout + out.stderr
    if "No activities found" in text or "aborted" in text.lower():
        raise MlxError(f"could not launch {pkg} — is it installed? ({text.strip()[:200]})")
    print(f"launched {pkg}")


def cmd_shell(dev: AdbDevice, args: list[str]) -> None:
    res = dev.shell(*args)
    sys.stdout.write(res.stdout)
    sys.stderr.write(res.stderr)


COMMANDS: dict[str, Callable[[AdbDevice, list[str]], None]] = {
    "screenshot": cmd_screenshot,
    "dump-ui": cmd_dump_ui,
    "find": cmd_find,
    "tap": cmd_tap,
    "text": cmd_text,
    "launch": cmd_launch,
    "shell": cmd_shell,
}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    fn = COMMANDS.get(cmd)
    if fn is None:
        print(f"unknown command: {cmd}\n{__doc__}", file=sys.stderr)
        return 2
    try:
        fn(_device(), rest)
    except MlxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
