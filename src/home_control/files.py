"""Read and write a JSON device file at a path the caller chooses."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from home_control.errors import ConfigError


def load_config_file(path: Path) -> dict[str, Any]:
    """Return the parsed file. Raises FileNotFoundError if it's missing, ConfigError if unusable."""
    mode = stat.S_IMODE(path.stat().st_mode)  # FileNotFoundError propagates
    if mode & 0o077:
        raise ConfigError(f"{path}: permissions {oct(mode)} are too open; run: chmod 600 {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{path}: cannot read: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a JSON object")
    return data


def save_config_file(path: Path, data: Mapping[str, Any]) -> None:
    """Write the file atomically with mode 600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".home-", suffix=".json")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
