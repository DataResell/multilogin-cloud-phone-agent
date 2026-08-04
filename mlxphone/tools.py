"""Agent-facing device tools — the step-2 primitives any agent calls over a shell.

    python -m mlxphone.tools screenshot [out.png]
    python -m mlxphone.tools dump-ui   [out.xml]
    python -m mlxphone.tools find      <keyword>
    python -m mlxphone.tools tap       <x> <y>
    python -m mlxphone.tools text      "<string>"
    python -m mlxphone.tools shell     <args...>

The connected device (serial + transient glogin code) is read from
``.mlxphone/device.json``, written by ``session start``. glogin is refreshed
before every action (the session expires in ~30-60s).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

from . import state
from .adb import AdbDevice
from .errors import MlxError

_FIELD_RE = re.compile(r'(text|content-desc|resource-id|bounds)="([^"]*)"')


def _device() -> AdbDevice:
    saved = state.load_device()
    if not saved:
        raise MlxError(
            "No connected device. Run: python -m mlxphone.session start --phone <id>"
        )
    return AdbDevice(saved["serial"], saved.get("pwd", ""), saved.get("adb_bin", "adb"))


def _screencap(dev: AdbDevice) -> bytes:
    return subprocess.run(
        [dev.adb_bin, "-s", dev.serial, "exec-out", "screencap", "-p"],
        capture_output=True,
        timeout=60,
    ).stdout


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
