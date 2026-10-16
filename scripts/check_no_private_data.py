#!/usr/bin/env python3
"""Fail if any private value from the owner's device files appears anywhere in this repo's git history.

Usage: python scripts/check_no_private_data.py [--repo PATH] [--also STRING ...] DENY_FILE [DENY_FILE ...]

DENY_FILEs are the owner's real device files (tinytuya devices.json, an application's home.json). They stay
outside the repo. Matches are reported redacted, so the output itself is safe to share.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SENSITIVE_KEYS = {"id", "key", "ip", "mac", "uuid", "sn", "name", "room", "aliases", "product_id", "local_key"}
ROOT = Path(__file__).resolve().parents[1]
MIN_LEN = 2  # shorter values can't be told apart from ordinary text
WORD_LEN = 4  # values shorter than this must match as whole words (e.g. a room called "Den")


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


def history_text(repo: Path) -> str:
    """Every commit's identity, message and patch (merges included), plus tag annotations."""
    log = ["git", "log", "--all", "-m", "-p", "--format=%H%n%an <%ae>%n%cn <%ce>%n%B"]
    tags = ["git", "for-each-ref", "refs/tags", "--format=%(refname) %(taggeremail) %(contents)"]
    return "\n".join(subprocess.run(c, cwd=repo, capture_output=True, text=True, check=True).stdout for c in (log, tags))


def found(value: str, text: str) -> bool:
    needle = value.casefold()
    if len(needle) >= WORD_LEN:
        return needle in text
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", text) is not None


def redact(value: str) -> str:
    return f"{value[:2]}…({len(value)} chars)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=ROOT, help="repository to scan (default: this one)")
    parser.add_argument("--also", action="append", default=[], help="extra private string (e.g. an email)")
    parser.add_argument("deny_files", nargs="+", type=Path)
    args = parser.parse_args(argv)
    try:
        values = deny_values(args.deny_files, args.also)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"cannot read deny file: {exc}", file=sys.stderr)
        return 2
    text = history_text(args.repo).casefold()
    hits = sorted(redact(v) for v in values if found(v, text))
    for hit in hits:
        print(f"private value found in git history: {hit}")
    print(f"checked {len(values)} private values: {'FAIL' if hits else 'clean'}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
