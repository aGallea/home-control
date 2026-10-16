#!/usr/bin/env python3
"""Fail if any private value from the owner's device files appears anywhere in this repo's git history.

Usage: python scripts/check_no_private_data.py [--also STRING ...] DENY_FILE [DENY_FILE ...]

DENY_FILEs are the owner's real device files (tinytuya devices.json, an application's home.json). They stay
outside the repo. Matches are reported redacted, so the output itself is safe to share.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SENSITIVE_KEYS = {"id", "key", "ip", "mac", "uuid", "sn", "name", "room", "aliases", "product_id", "local_key"}
MIN_LEN = 4


def _collect(node: Any, out: set[str], sensitive: bool = False) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "rooms" and isinstance(v, dict):
                out.update(str(room) for room in v)
            _collect(v, out, sensitive or k in SENSITIVE_KEYS or k == "connection")
    elif isinstance(node, list):
        for v in node:
            _collect(v, out, sensitive)
    elif sensitive and isinstance(node, str) and len(node) >= MIN_LEN:
        out.add(node)


def deny_values(paths: list[Path], also: list[str]) -> set[str]:
    values = {a for a in also if len(a) >= MIN_LEN}
    for path in paths:
        _collect(json.loads(path.read_text(encoding="utf-8")), values)
    return values


def history_text() -> str:
    cmd = ["git", "log", "--all", "-p", "--format=%H%n%an <%ae>%n%cn <%ce>%n%B"]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def redact(value: str) -> str:
    return f"{value[:2]}…({len(value)} chars)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--also", action="append", default=[], help="extra private string (e.g. an email)")
    parser.add_argument("deny_files", nargs="+", type=Path)
    args = parser.parse_args(argv)
    values = deny_values(args.deny_files, args.also)
    text = history_text().casefold()
    hits = sorted(redact(v) for v in values if v.casefold() in text)
    for hit in hits:
        print(f"private value found in git history: {hit}")
    print(f"checked {len(values)} private values: {'FAIL' if hits else 'clean'}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
