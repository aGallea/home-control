# home-control: Generic Config + GitHub Release — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `home-control` as a generic, config-agnostic library with no private data. Publish it from a clean public GitHub repo as a release wheel, and switch reachy-lychee to own its `home.json` and depend on the pinned wheel.

**Architecture:**
- `Home.from_config(dict)` validates a versioned JSON schema in which each device has a `type`, `backend`, `connection` and `options`. Backends come from a registry and validate their own `connection`/`options`.
- File helpers take explicit paths, and the library never chooses a location.
- A privacy test and a pre-push deny-list check keep the public repo free of private data.
- Lychee resolves its own `home.json` path, passes the parsed data to `Home.from_config`, and installs home-control from the GitHub Release URL.

**Tech Stack:** Python ≥ 3.11, tinytuya 1.17.x, pytest + pytest-asyncio, ruff, mypy (strict), uv, GitHub Actions (`actions/checkout@v4`, `astral-sh/setup-uv@v5`), `gh`.

**Spec:** `docs/superpowers/specs/2026-10-16-home-control-generic-config-design.md`

## Global Constraints

**Locations used in this plan:**
- `$HC`: the home-control checkout.
- `$APPS`: the reachy-mini-apps checkout.
- `$LYCHEE`: `$APPS/reachy_lychee`.

Never write absolute local paths, real device data, room names or people's names into any committed file, commit message, PR text or release note.

**Privacy:**
- No private-range IPv4 addresses (`10.x`, `172.16–31.x`, `192.168.x`) anywhere in the repo. Examples use `192.0.2.0/24`.
- The only email addresses allowed in files: `5315995+aGallea@users.noreply.github.com` and `noreply@anthropic.com` (commit trailer).
- home-control commit author and committer: `aGallea <5315995+aGallea@users.noreply.github.com>`, set in `$HC`'s local git config.
- Example devices are made up: "Kitchen left", "Kitchen right", "Hall", room "Kitchen" (alias "המטבח"), ids `dev-…`, keys `0123456789abcdef`.

**Behaviour carried over from phase 1 (must not regress):**
- LAN values on DPS `"1"`: UP → `"on"`, DOWN → `"off"`, STOP → `"stop"`; `inverted` swaps on/off. Never send `open`/`close`.
- A move is `OK` only if the reply's `dps["1"]` equals the value sent.
- Error codes `901`/`902`/`905` and `914` (no reply after connecting) → `UNREACHABLE`; any other code → `REJECTED`.
- Timeout 3 s, `connection_retry_limit=2`, `connection_retry_delay=0`, default protocol version `3.3`.
- The tinytuya logger is set to INFO when the backend module is imported.
- Failed moves are logged as warnings; `UNREACHABLE` ones add the hint "run: home-control scan".
- Normalization: map `’‘ʼ׳´` and backtick to `'`, collapse whitespace, casefold.

**Schema:**
- `version` must be `1`.
- Known types: `{"shutter"}`. Known backends: `{"tuya_lan"}`.
- A device with an unknown type or backend is skipped and recorded in `Home.skipped`; it is not an error.
- The reserved target `all` can't be used as a device name, room name or alias.

**Style:**
- **home-control:** ruff line-length 119 with E501 ignored, rules E/F/W/I/C4; mypy strict on `src/`.
- **lychee:** existing config. Lint only the files you touch; tests don't need docstrings.

**Commits:**
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Branches:**
  - `$HC`: new history on `main` (the old repo is deleted, as the user approved). The first push is `main`, then the tag.
  - `$APPS`: continue on `feat/lychee-home-shutters`.

## Review Focus

1. **A config written for a newer home-control** (a `light` device with backend `zigbee2mqtt`) loads, drives the shutters, and lists the unknown device in `skipped` with a reason. It doesn't crash lychee. Pinned in Task 3: `test_unknown_type_and_backend_are_skipped`. Task 8: `test_build_home_logs_skipped_devices`.
2. **A target that only names non-shutter devices** (once lights exist) → `UnknownTargetError` listing shutter targets, and nothing moves. Pinned in Task 5: `test_move_ignores_non_shutter_devices`.
3. **A device's printed form would show its key** → `repr(device)` never contains `connection` or `options` values. Pinned in Task 2: `test_device_repr_hides_connection`.
4. **`scan` rewriting the file loses fields it doesn't understand** (future options, rooms, skipped devices) → only `connection.ip` changes. Pinned in Task 6: `test_scan_preserves_unknown_fields`.
5. **The robot's dependency helper drops the URL** and pip resolves `home-control` from PyPI → the helper prints `home-control @ <url>`. Pinned in Task 7: `test_helper_keeps_direct_url`.

---

## File Structure

**home-control** (`$HC`):

| File | Responsibility |
|---|---|
| `pyproject.toml`, `.gitignore`, `README.md`, `LICENSE` | Package metadata (no `tomli-w`), docs, MIT license |
| `.github/workflows/ci.yml` | Tests, ruff and mypy on every push and PR |
| `.github/workflows/release.yml` | On tag `v*`: test, `uv build`, GitHub Release with the wheel and sdist |
| `scripts/check_no_private_data.py` | Pre-push deny-list scan of the whole git history |
| `src/home_control/errors.py` | `ConfigError`, `UnknownTargetError` |
| `src/home_control/models.py` | `normalize_name`, `Direction`, `Outcome`, `CommandResult`, `Device`, `SHUTTER` |
| `src/home_control/files.py` | `load_config_file`, `save_config_file` |
| `src/home_control/backends/base.py` | `Backend` protocol, `BackendError` |
| `src/home_control/backends/tuya_lan.py` | `TuyaLanBackend`, `command_value`, `interpret_reply` |
| `src/home_control/backends/__init__.py` | `default_backends()` registry |
| `src/home_control/config.py` | `parse_config` → `ParsedConfig` |
| `src/home_control/home.py` | `Home` (+ `from_config`) |
| `src/home_control/cli.py` | `home-control --config PATH …` |
| `tests/…` | One test file per module, plus `test_privacy.py` |

**reachy-mini-apps** (`$APPS`):

| File | Change |
|---|---|
| `reachy_lychee/pyproject.toml` | Pinned wheel URL; drop `[tool.uv.sources]` |
| `reachy_lychee/scripts/deps_without.py` | Keep direct URLs |
| `reachy_lychee/scripts/install_on_robot.sh` | Drop the home-control rsync and `--no-deps` |
| `reachy_lychee/src/reachy_lychee/main.py` | `home_config_path`, `build_home(instance_path, path=None)` |
| `reachy_lychee/src/reachy_lychee/tools/home.py` | `device_name`; `list` passes through the new shape |
| `reachy_lychee/README.md` | Home control section |
| Tests | `tests/home/test_wiring.py`, `tests/tools/test_home.py`, `tests/test_deps_without.py` |

---

### Task 1: Fresh repository with privacy guard

**Files:**
- Delete:
  - `$HC/.git` (after a bundle backup outside the repo);
  - `$HC/src`, `$HC/tests`, `$HC/uv.lock`;
  - the phase-1 spec and plan in `$HC/docs/superpowers/` (`*-home-control-shutters*`).
- Create: `pyproject.toml`, `.gitignore`, `README.md`, `LICENSE`, `src/home_control/__init__.py`, `tests/test_privacy.py`, `.github/workflows/ci.yml`, `scripts/check_no_private_data.py`
- Keep: the generic spec and this plan

**Interfaces:**
- Produces: `uv run pytest` green on a clean tree; `scripts/check_no_private_data.py [--also STR ...] DENY_FILE ...` (exit 0 if clean, 1 on hits, 2 on usage error).

- [ ] **Step 1: Back up and reset**

```bash
cd $HC
git bundle create "$SCRATCH/home-control-phase1.bundle" --all   # $SCRATCH = a private scratch dir outside any repo
rm -rf .git src tests uv.lock .venv
rm -f docs/superpowers/specs/*-home-control-shutters-design.md docs/superpowers/plans/*-home-control-shutters.md
git init -b main
git config user.name "aGallea"
git config user.email "5315995+aGallea@users.noreply.github.com"
mkdir -p src/home_control/backends tests scripts .github/workflows
```

- [ ] **Step 2: Scaffold files**

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "home-control"
version = "0.2.0"
description = "Local-only control of home devices (Tuya LAN shutters), configured by the caller."
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
dependencies = ["tinytuya>=1.17,<1.18"]

[project.urls]
Source = "https://github.com/aGallea/home-control"

[project.scripts]
home-control = "home_control.cli:main"

[dependency-groups]
dev = ["pytest", "pytest-asyncio", "ruff", "mypy"]

[tool.setuptools]
package-dir = { "" = "src" }

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 119

[tool.ruff.lint]
select = ["E", "F", "W", "I", "C4"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.11"
files = ["src/"]
strict = true
ignore_missing_imports = true
```

`.gitignore`:

```
.venv/
__pycache__/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
dist/
build/
.superpowers/
# device files hold keys and never belong in this repo
*.toml.local
home.json
devices.json
devices.toml
```

`LICENSE`: the standard MIT license text, with the line `Copyright (c) 2026 aGallea`.

`README.md`:

````markdown
# home-control

Local-only control of home devices. No cloud. Today it drives Tuya Wi-Fi curtain/shutter switches over the LAN (`tuya_lan`).
The library holds no device data: the application using it owns a JSON device file and passes its contents in.

## Install

```
pip install "home-control @ https://github.com/aGallea/home-control/releases/download/v0.2.0/home_control-0.2.0-py3-none-any.whl"
```

## Use

```python
from home_control import Home, load_config_file

home = Home.from_config(load_config_file(path_you_choose))
await home.down("Kitchen")
```

## Device file (version 1)

```json
{
  "version": 1,
  "rooms": {"Kitchen": {"aliases": ["המטבח"]}},
  "devices": [
    {
      "name": "Kitchen left",
      "room": "Kitchen",
      "type": "shutter",
      "backend": "tuya_lan",
      "connection": {"id": "dev-kitchen-left", "ip": "192.0.2.10", "key": "0123456789abcdef", "version": 3.3},
      "options": {"inverted": false}
    }
  ]
}
```

Keep the file readable only by you (`chmod 600`); it holds local keys. Devices with a `type` or `backend` this version doesn't know are skipped and listed in `Home.skipped`.

## CLI

```
home-control --config path/to/home.json list
home-control --config path/to/home.json down Kitchen
home-control --config path/to/home.json status all
home-control --config path/to/home.json import tinytuya-devices.json
home-control --config path/to/home.json scan
```

`HOME_CONTROL_CONFIG` can stand in for `--config`.

## Contributing

Never commit device data. Before pushing, run:

```
python scripts/check_no_private_data.py --also you@example.com path/to/your/home.json path/to/tinytuya-devices.json
```
````

`src/home_control/__init__.py`:

```python
"""Local-only home control."""
```

`.github/workflows/ci.yml`:

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run pytest -q
      - run: uv run ruff check .
      - run: uv run mypy
```

- [ ] **Step 3: Write the failing privacy test** (`tests/test_privacy.py`)

```python
"""Guard: this repo is public and must contain no private data."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_EMAILS = {"5315995+agallea@users.noreply.github.com", "noreply@anthropic.com", "noreply@github.com"}
PRIVATE_IP = re.compile(r"\b(?:10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def _tracked_text_files() -> list[Path]:
    files = []
    for name in _git("ls-files", "--cached", "--others", "--exclude-standard").splitlines():
        path = ROOT / name
        if path.is_file():
            try:
                path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            files.append(path)
    return files


def test_no_private_ip_addresses():
    hits = [f"{p.relative_to(ROOT)}: {m}" for p in _tracked_text_files() for m in PRIVATE_IP.findall(p.read_text())]
    assert hits == []


def test_no_foreign_email_addresses():
    hits = [
        f"{p.relative_to(ROOT)}: {m}"
        for p in _tracked_text_files()
        for m in EMAIL.findall(p.read_text())
        if m.casefold() not in ALLOWED_EMAILS and not m.endswith(("@github.com", "@example.com"))
    ]
    assert hits == []


def test_commit_identities_are_noreply():
    proc = subprocess.run(["git", "log", "--all", "--format=%ae%n%ce"], cwd=ROOT, capture_output=True, text=True)
    emails = set(proc.stdout.split()) if proc.returncode == 0 else set()  # no commits yet -> nothing to check
    assert {e.casefold() for e in emails} <= ALLOWED_EMAILS
```

Note: addresses at `github.com` and `example.com` are allowed because they aren't personal. `noreply@github.com` is the committer GitHub uses on PR merge commits in CI.

- [ ] **Step 4: Run it to verify it fails**

```bash
cd $HC && printf 'x = "192.%s.1.5"\n' 168 > tests/_leak_probe.py && uv sync -q && uv run pytest tests/test_privacy.py -q; rm tests/_leak_probe.py
```

Expected: `test_no_private_ip_addresses` FAILS, listing the probe file. `test_commit_identities_are_noreply` passes, because there are no commits yet.

- [ ] **Step 5: Write the pre-push check** (`scripts/check_no_private_data.py`)

```python
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
```

- [ ] **Step 6: Run checks, then commit**

```bash
cd $HC && uv run pytest -q && uv run ruff check . && uv run mypy
git add -A && git status --short
git commit -m "chore: project scaffold, privacy guard, CI

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
uv run pytest tests/test_privacy.py -q
python3 scripts/check_no_private_data.py --also "$OWNER_EMAIL" "$TINYTUYA_DEVICES_JSON" "$OLD_DEVICES_TOML_AS_JSON"
```

(`$OWNER_EMAIL` and the deny-file paths are supplied by the executor at run time; they must never be written into the repo. For an old TOML device file, convert it to JSON in `$SCRATCH` first.)

Expected: 3 privacy tests pass, including the commit-identity test now that a commit exists. Ruff and mypy are clean. The check script prints `clean`.

---

### Task 2: Errors, models, file helpers

**Files:**
- Create: `src/home_control/errors.py`, `src/home_control/models.py`, `src/home_control/files.py`
- Modify: `src/home_control/__init__.py`
- Test: `tests/test_models.py`, `tests/test_files.py`

**Interfaces:**
- Produces:
  - `ConfigError(ValueError)`
  - `UnknownTargetError(LookupError)` (`.target: str`, `.valid: list[str]`; message `unknown target '<t>'; valid: a, b`)
  - `normalize_name(str) -> str`
  - `Direction` (`UP`/`DOWN`/`STOP`, values `up`/`down`/`stop`)
  - `Outcome` (`OK`/`UNREACHABLE`/`NOT_CONFIRMED`/`REJECTED`, values `ok`/`unreachable`/`not_confirmed`/`rejected`)
  - `CommandResult(device_name: str, outcome: Outcome, detail: str | None = None)` with `.ok`
  - `SHUTTER = "shutter"`
  - `Device` (frozen: `name: str`, `room: str`, `type: str`, `backend: str`, `aliases: tuple[str, ...] = ()`, `connection: Mapping[str, Any]` (repr=False), `options: Mapping[str, Any]` (repr=False))
  - `load_config_file(path: Path) -> dict[str, Any]`
  - `save_config_file(path: Path, data: Mapping[str, Any]) -> None`

- [ ] **Step 1: Write the failing tests**

`tests/test_models.py`:

```python
from dataclasses import FrozenInstanceError

import pytest

from home_control.models import SHUTTER, CommandResult, Device, Direction, Outcome, normalize_name


def _device(**kw):
    base = dict(name="Kitchen left", room="Kitchen", type=SHUTTER, backend="tuya_lan",
                connection={"id": "dev-kitchen-left", "ip": "192.0.2.10", "key": "0123456789abcdef"})
    base.update(kw)
    return Device(**base)


def test_normalize_collapses_whitespace_casefolds_and_unifies_apostrophes():
    assert normalize_name("  Kid’s   ROOM ") == "kid's room"
    assert normalize_name("Kidʼs room") == "kid's room"
    assert normalize_name("ג׳ינס  חדר") == "ג'ינס חדר"


def test_direction_and_outcome_values():
    assert [d.value for d in Direction] == ["up", "down", "stop"]
    assert [o.value for o in Outcome] == ["ok", "unreachable", "not_confirmed", "rejected"]


def test_command_result_ok():
    assert CommandResult("Kitchen left", Outcome.OK).ok
    assert not CommandResult("Kitchen left", Outcome.UNREACHABLE, "timeout").ok


def test_device_defaults_and_frozen():
    d = _device()
    assert d.aliases == () and d.options == {}
    with pytest.raises(FrozenInstanceError):
        d.name = "x"  # type: ignore[misc]


def test_device_repr_hides_connection():
    text = repr(_device(options={"inverted": True}))
    assert "0123456789abcdef" not in text and "192.0.2.10" not in text and "inverted" not in text
    assert "Kitchen left" in text
```

`tests/test_files.py`:

```python
import json
import os
import stat

import pytest

from home_control.errors import ConfigError
from home_control.files import load_config_file, save_config_file


def _write(tmp_path, text, mode=0o600):
    p = tmp_path / "home.json"
    p.write_text(text, encoding="utf-8")
    p.chmod(mode)
    return p


def test_load_valid_json(tmp_path):
    assert load_config_file(_write(tmp_path, '{"version": 1, "devices": []}')) == {"version": 1, "devices": []}


def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config_file(tmp_path / "nope.json")


def test_too_open_permissions_rejected(tmp_path):
    with pytest.raises(ConfigError, match="permissions"):
        load_config_file(_write(tmp_path, "{}", mode=0o644))


def test_invalid_json_rejected(tmp_path):
    with pytest.raises(ConfigError, match="JSON"):
        load_config_file(_write(tmp_path, "{nope"))


def test_non_object_rejected(tmp_path):
    with pytest.raises(ConfigError, match="object"):
        load_config_file(_write(tmp_path, "[1, 2]"))


def test_unreadable_rejected(tmp_path):
    d = tmp_path / "dir.json"
    d.mkdir(mode=0o700)
    with pytest.raises(ConfigError, match="cannot read"):
        load_config_file(d)


def test_non_utf8_rejected(tmp_path):
    p = tmp_path / "home.json"
    p.write_bytes(b"\xff\xfe{}")
    p.chmod(0o600)
    with pytest.raises(ConfigError, match="cannot read"):
        load_config_file(p)


def test_save_is_atomic_mode_600_and_roundtrips(tmp_path):
    path = tmp_path / "sub" / "home.json"
    data = {"version": 1, "rooms": {"Kitchen": {"aliases": ["המטבח"]}}, "devices": []}
    save_config_file(path, data)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert "המטבח" in path.read_text(encoding="utf-8")  # not \u-escaped
    assert load_config_file(path) == data
    assert [p.name for p in path.parent.iterdir()] == ["home.json"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_models.py tests/test_files.py -q`
Expected: collection errors, `No module named 'home_control.models'` / `'home_control.files'`

- [ ] **Step 3: Implement**

`src/home_control/errors.py`:

```python
"""Exceptions raised by home-control."""

from __future__ import annotations


class ConfigError(ValueError):
    """The device configuration is invalid."""


class UnknownTargetError(LookupError):
    """A target matched no device, room, or 'all'."""

    def __init__(self, target: str, valid: list[str]) -> None:
        super().__init__(f"unknown target '{target}'; valid: {', '.join(valid)}")
        self.target = target
        self.valid = valid
```

`src/home_control/models.py`:

```python
"""Core data types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

SHUTTER = "shutter"

# Typographic apostrophes (LLM/STT output) and the Hebrew geresh all compare as "'".
_APOSTROPHES = str.maketrans(dict.fromkeys("’‘ʼ׳´`", "'"))


def normalize_name(value: str) -> str:
    """Return the comparison key for a name: unified apostrophes, collapsed whitespace, casefolded."""
    return " ".join(value.translate(_APOSTROPHES).split()).casefold()


class Direction(Enum):
    """Shutter movement command."""

    UP = "up"
    DOWN = "down"
    STOP = "stop"


class Outcome(Enum):
    """Result of one command on one device."""

    OK = "ok"
    UNREACHABLE = "unreachable"
    NOT_CONFIRMED = "not_confirmed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a command sent to one device."""

    device_name: str
    outcome: Outcome
    detail: str | None = None

    @property
    def ok(self) -> bool:
        """True when the device confirmed the command."""
        return self.outcome is Outcome.OK


@dataclass(frozen=True)
class Device:
    """One controllable device. `connection` and `options` are backend-specific and never printed."""

    name: str
    room: str
    type: str
    backend: str
    connection: Mapping[str, Any] = field(repr=False)
    aliases: tuple[str, ...] = ()
    options: Mapping[str, Any] = field(default_factory=dict, repr=False)
```

(Field order: `connection` comes before the defaulted fields, so it can have no default. `_device()` in the tests passes it by keyword.)

`src/home_control/files.py`:

```python
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
```

`src/home_control/__init__.py`:

```python
"""Local-only home control."""

from home_control.errors import ConfigError, UnknownTargetError
from home_control.files import load_config_file, save_config_file
from home_control.models import SHUTTER, CommandResult, Device, Direction, Outcome, normalize_name

__all__ = [
    "SHUTTER",
    "CommandResult",
    "ConfigError",
    "Device",
    "Direction",
    "Outcome",
    "UnknownTargetError",
    "load_config_file",
    "normalize_name",
    "save_config_file",
]
```

- [ ] **Step 4: Run all checks**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass (privacy 3 + models 5 + files 8 = 16); ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: errors, device model and JSON file helpers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Backend protocol, Tuya LAN backend, registry

**Files:**
- Create: `src/home_control/backends/base.py`, `src/home_control/backends/tuya_lan.py`, `src/home_control/backends/__init__.py`
- Modify: `src/home_control/__init__.py`
- Test: `tests/test_tuya_lan.py`

**Interfaces:**
- Consumes: `Device`, `Direction`, `Outcome`, `CommandResult`, `ConfigError` (Task 2)
- Produces:
  - `BackendError(Exception)` (`.outcome`, `.detail`)
  - `Backend` (Protocol):
    - `validate(device: Device) -> None` (raises `ConfigError`)
    - `async move(device, direction) -> CommandResult` (never raises)
    - `async status(device) -> dict[str, Any]` (raises `BackendError`)
  - `TuyaLanBackend(timeout_s=3.0, attempts=2, device_factory=None)`, with `_make_device(device)`
  - `command_value(direction, inverted) -> str`
  - `interpret_reply(device_name, sent, reply) -> CommandResult`
  - `default_backends() -> dict[str, Backend]` returning `{"tuya_lan": TuyaLanBackend()}`

- [ ] **Step 1: Write the failing tests** (`tests/test_tuya_lan.py`)

```python
import logging
from unittest.mock import MagicMock

import pytest

from home_control.backends import default_backends
from home_control.backends.base import BackendError
from home_control.backends.tuya_lan import TuyaLanBackend, command_value, interpret_reply
from home_control.errors import ConfigError
from home_control.models import SHUTTER, Device, Direction, Outcome

CONN = {"id": "dev-kitchen-left", "ip": "192.0.2.10", "key": "0123456789abcdef"}


def _device(connection=None, options=None):
    return Device("Kitchen left", "Kitchen", SHUTTER, "tuya_lan", dict(CONN if connection is None else connection),
                  options=options or {})


def _backend(device_obj):
    made = []

    def factory(d):
        made.append(d)
        return device_obj

    return TuyaLanBackend(device_factory=factory), made


def test_registry_has_tuya_lan():
    assert isinstance(default_backends()["tuya_lan"], TuyaLanBackend)


def test_validate_accepts_minimal_and_full():
    b = TuyaLanBackend()
    b.validate(_device())
    b.validate(_device({**CONN, "version": 3.4}, {"inverted": True}))


@pytest.mark.parametrize("field", ["id", "ip", "key"])
def test_validate_requires_connection_fields(field):
    conn = {k: v for k, v in CONN.items() if k != field}
    with pytest.raises(ConfigError, match=rf"Kitchen left.*connection\.{field}"):
        TuyaLanBackend().validate(_device(conn))


def test_validate_rejects_bad_version_and_option():
    with pytest.raises(ConfigError, match=r"connection\.version"):
        TuyaLanBackend().validate(_device({**CONN, "version": "3.3"}))
    with pytest.raises(ConfigError, match=r"options\.inverted"):
        TuyaLanBackend().validate(_device(options={"inverted": "yes"}))


def test_command_values():
    assert [command_value(d, False) for d in Direction] == ["on", "off", "stop"]
    assert [command_value(d, True) for d in Direction] == ["off", "on", "stop"]


def test_interpret_confirmed():
    assert interpret_reply("Kitchen left", "on", {"dps": {"1": "on"}}).outcome is Outcome.OK


def test_interpret_none_and_other_value_not_confirmed():
    assert interpret_reply("Kitchen left", "on", None).outcome is Outcome.NOT_CONFIRMED
    r = interpret_reply("Kitchen left", "on", {"dps": {"1": "stop"}})
    assert r.outcome is Outcome.NOT_CONFIRMED and "stop" in (r.detail or "")


@pytest.mark.parametrize("code", ["901", "902", "905"])
def test_network_errors_unreachable(code):
    r = interpret_reply("Kitchen left", "on", {"Error": "Network Error", "Err": code, "Payload": None})
    assert r.outcome is Outcome.UNREACHABLE and code in (r.detail or "")


def test_no_reply_after_connect_is_unreachable():
    r = interpret_reply("Kitchen left", "on", {"Error": "Check device key or version", "Err": "914", "Payload": None})
    assert r.outcome is Outcome.UNREACHABLE
    assert "no reply" in (r.detail or "") and "914" in (r.detail or "")


def test_other_errors_rejected():
    r = interpret_reply("Kitchen left", "on", {"Error": "Invalid Payload", "Err": "904", "Payload": None})
    assert r.outcome is Outcome.REJECTED and "904" in (r.detail or "")


async def test_move_sends_on_off_stop_to_dps_1_and_respects_inverted():
    dev = MagicMock()
    dev.set_value.side_effect = lambda idx, val: {"dps": {idx: val}}
    backend, made = _backend(dev)
    for d in Direction:
        assert (await backend.move(_device(), d)).ok
    await backend.move(_device(options={"inverted": True}), Direction.UP)
    assert [c.args for c in dev.set_value.call_args_list] == [("1", "on"), ("1", "off"), ("1", "stop"), ("1", "off")]
    assert made[0].name == "Kitchen left"


async def test_move_exception_is_unreachable():
    dev = MagicMock()
    dev.set_value.side_effect = OSError("no route to host")
    backend, _ = _backend(dev)
    r = await backend.move(_device(), Direction.DOWN)
    assert r.outcome is Outcome.UNREACHABLE and "no route to host" in (r.detail or "")


async def test_status_returns_dps_or_raises():
    dev = MagicMock()
    dev.status.return_value = {"dps": {"1": "stop", "9": 40}}
    backend, _ = _backend(dev)
    assert await backend.status(_device()) == {"1": "stop", "9": 40}
    dev.status.return_value = {"Error": "Network Error: Device Unreachable", "Err": "905", "Payload": None}
    with pytest.raises(BackendError) as exc:
        await backend.status(_device())
    assert exc.value.outcome is Outcome.UNREACHABLE


def test_default_factory_builds_tinytuya_device(monkeypatch):
    calls = {}

    class FakeDevice:
        def __init__(self, *args, **kwargs):
            calls["args"], calls["kwargs"] = args, kwargs

    monkeypatch.setattr("home_control.backends.tuya_lan.tinytuya.Device", FakeDevice)
    TuyaLanBackend()._make_device(_device({**CONN, "version": 3.4}))
    assert calls["args"] == ("dev-kitchen-left", "192.0.2.10", "0123456789abcdef")
    assert calls["kwargs"] == {
        "version": 3.4, "connection_timeout": 3.0, "connection_retry_limit": 2, "connection_retry_delay": 0,
    }


def test_tinytuya_logger_capped_at_info():
    assert logging.getLogger("tinytuya").level == logging.INFO
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_tuya_lan.py -q`
Expected: collection error `No module named 'home_control.backends'`

- [ ] **Step 3: Implement**

`src/home_control/backends/base.py`:

```python
"""Backend interface."""

from __future__ import annotations

from typing import Any, Protocol

from home_control.models import CommandResult, Device, Direction, Outcome


class BackendError(Exception):
    """A status call failed (move returns a CommandResult instead)."""

    def __init__(self, outcome: Outcome, detail: str) -> None:
        super().__init__(f"{outcome.value}: {detail}")
        self.outcome = outcome
        self.detail = detail


class Backend(Protocol):
    """Talks to devices of one kind of connection."""

    def validate(self, device: Device) -> None:
        """Check the device's connection/options; raise ConfigError naming the device and field."""
        ...

    async def move(self, device: Device, direction: Direction) -> CommandResult:
        """Move or stop a shutter; never raises."""
        ...

    async def status(self, device: Device) -> dict[str, Any]:
        """Return raw device state; raise BackendError on failure."""
        ...
```

`src/home_control/backends/tuya_lan.py`:

```python
"""Tuya LAN backend (tinytuya). No cloud."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import tinytuya

from home_control.backends.base import BackendError
from home_control.errors import ConfigError
from home_control.models import CommandResult, Device, Direction, Outcome

DPS_CONTROL = "1"
# Tuya curtain switches over LAN: on = up, off = down. The cloud's open/close are acked and silently ignored.
_VALUES = {Direction.UP: "on", Direction.DOWN: "off", Direction.STOP: "stop"}
_UNREACHABLE_CODES = {str(tinytuya.ERR_CONNECT), str(tinytuya.ERR_TIMEOUT), str(tinytuya.ERR_OFFLINE)}
# tinytuya reports "connected, then no reply" as ERR_KEY_OR_VER; on 3.3 a wrong key looks the same.
_NO_REPLY_CODE = str(tinytuya.ERR_KEY_OR_VER)

# tinytuya logs local keys at DEBUG; never let a DEBUG root logger pass them through.
logging.getLogger("tinytuya").setLevel(logging.INFO)


def command_value(direction: Direction, inverted: bool) -> str:
    """Return the DPS 1 value for a direction, swapping on/off for inverted motors."""
    if inverted and direction is not Direction.STOP:
        direction = Direction.DOWN if direction is Direction.UP else Direction.UP
    return _VALUES[direction]


def _error_of(reply: Any) -> tuple[Outcome, str] | None:
    if isinstance(reply, dict) and "Err" in reply:
        code = str(reply.get("Err"))
        if code == _NO_REPLY_CODE:
            return Outcome.UNREACHABLE, f"no reply after connecting: device busy, or wrong key/version (code {code})"
        outcome = Outcome.UNREACHABLE if code in _UNREACHABLE_CODES else Outcome.REJECTED
        return outcome, f"{reply.get('Error', 'error')} (code {code})"
    return None


def interpret_reply(device_name: str, sent: str, reply: Any) -> CommandResult:
    """Map a tinytuya set_value reply to a CommandResult."""
    error = _error_of(reply)
    if error:
        return CommandResult(device_name, error[0], error[1])
    if reply is None:
        return CommandResult(device_name, Outcome.NOT_CONFIRMED, "device acknowledged but sent no new state")
    state = reply.get("dps", {}).get(DPS_CONTROL) if isinstance(reply, dict) else None
    if state == sent:
        return CommandResult(device_name, Outcome.OK)
    return CommandResult(device_name, Outcome.NOT_CONFIRMED, f"device reported '{state}' instead of '{sent}'")


def _require_str(device: Device, field: str) -> None:
    value = device.connection.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"device '{device.name}': connection.{field} must be a non-empty string")


class TuyaLanBackend:
    """Tuya Wi-Fi curtain switches over the LAN."""

    def __init__(
        self,
        timeout_s: float = 3.0,
        attempts: int = 2,
        device_factory: Callable[[Device], Any] | None = None,
    ) -> None:
        self._timeout_s = timeout_s
        self._attempts = attempts
        self._factory = device_factory or self._make_device

    def validate(self, device: Device) -> None:
        """Require connection.id/ip/key; check connection.version and options.inverted types."""
        for field in ("id", "ip", "key"):
            _require_str(device, field)
        version = device.connection.get("version", 3.3)
        if not isinstance(version, (int, float)) or isinstance(version, bool):
            raise ConfigError(f"device '{device.name}': connection.version must be a number")
        if not isinstance(device.options.get("inverted", False), bool):
            raise ConfigError(f"device '{device.name}': options.inverted must be true or false")

    def _make_device(self, device: Device) -> Any:
        conn = device.connection
        return tinytuya.Device(
            conn["id"],
            conn["ip"],
            conn["key"],
            version=float(conn.get("version", 3.3)),
            connection_timeout=self._timeout_s,
            connection_retry_limit=self._attempts,
            connection_retry_delay=0,
        )

    async def move(self, device: Device, direction: Direction) -> CommandResult:
        """Send one movement command; never raises."""
        value = command_value(direction, bool(device.options.get("inverted", False)))
        try:
            reply = await asyncio.to_thread(lambda: self._factory(device).set_value(DPS_CONTROL, value))
        except Exception as exc:  # tinytuya mostly returns error dicts, but sockets can still raise
            return CommandResult(device.name, Outcome.UNREACHABLE, f"{type(exc).__name__}: {exc}")
        return interpret_reply(device.name, value, reply)

    async def status(self, device: Device) -> dict[str, Any]:
        """Return the device's DPS values."""
        try:
            reply = await asyncio.to_thread(lambda: self._factory(device).status())
        except Exception as exc:
            raise BackendError(Outcome.UNREACHABLE, f"{type(exc).__name__}: {exc}") from exc
        error = _error_of(reply)
        if error:
            raise BackendError(*error)
        if not isinstance(reply, dict) or not isinstance(reply.get("dps"), dict):
            raise BackendError(Outcome.NOT_CONFIRMED, f"unexpected status reply: {reply!r}")
        return dict(reply["dps"])
```

`src/home_control/backends/__init__.py`:

```python
"""Device backends."""

from home_control.backends.base import Backend, BackendError
from home_control.backends.tuya_lan import TuyaLanBackend


def default_backends() -> dict[str, Backend]:
    """Backends this version can drive, by config name."""
    return {"tuya_lan": TuyaLanBackend()}


__all__ = ["Backend", "BackendError", "TuyaLanBackend", "default_backends"]
```

Add `Backend`, `BackendError`, `TuyaLanBackend`, `default_backends` to `src/home_control/__init__.py` (import from `home_control.backends`) and to `__all__`.

- [ ] **Step 4: Run all checks**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass; ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: backend protocol, Tuya LAN backend and registry

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Config schema parsing

**Files:**
- Create: `src/home_control/config.py`
- Modify: `src/home_control/__init__.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `Device`, `SHUTTER`, `normalize_name`, `ConfigError` (Task 2); `Backend` (Task 3)
- Produces:
  - `KNOWN_TYPES = frozenset({"shutter"})`, `ALL = "all"`
  - `ParsedConfig` (frozen):
    - `devices: tuple[Device, ...]`
    - `rooms: dict[str, tuple[str, ...]]` (display name → aliases, only rooms that have devices)
    - `skipped: tuple[tuple[str, str], ...]` (device name, reason)
  - `parse_config(data: Mapping[str, Any], backends: Mapping[str, Backend]) -> ParsedConfig`
- Room display name: the `rooms` key if it matches the device's room after normalization; otherwise the first device's spelling.

- [ ] **Step 1: Write the failing tests** (`tests/test_config.py`)

```python
import copy

import pytest

from home_control.backends import default_backends
from home_control.config import parse_config
from home_control.errors import ConfigError

CONN = {"id": "dev-kitchen-left", "ip": "192.0.2.10", "key": "0123456789abcdef"}
BASE = {
    "version": 1,
    "rooms": {"Kitchen": {"aliases": ["המטבח"]}},
    "devices": [
        {"name": "Kitchen left", "aliases": ["מטבח שמאל"], "room": "Kitchen", "type": "shutter",
         "backend": "tuya_lan", "connection": dict(CONN)},
        {"name": "Kitchen right", "room": "kitchen", "type": "shutter", "backend": "tuya_lan",
         "connection": {**CONN, "id": "dev-kitchen-right", "ip": "192.0.2.11"}, "options": {"inverted": True}},
        {"name": "Hall", "room": "Hall", "type": "shutter", "backend": "tuya_lan",
         "connection": {**CONN, "id": "dev-hall", "ip": "192.0.2.12"}},
    ],
}


def _parse(data):
    return parse_config(data, default_backends())


def _with(mutate):
    data = copy.deepcopy(BASE)
    mutate(data)
    return data


def test_valid_config():
    cfg = _parse(BASE)
    assert [d.name for d in cfg.devices] == ["Kitchen left", "Kitchen right", "Hall"]
    assert cfg.devices[0].aliases == ("מטבח שמאל",)
    assert cfg.devices[1].room == "Kitchen"  # normalized to the rooms-section spelling
    assert cfg.devices[1].options == {"inverted": True}
    assert cfg.rooms == {"Kitchen": ("המטבח",), "Hall": ()}
    assert cfg.skipped == ()


def test_device_named_like_its_single_device_room_is_allowed():
    assert [d.name for d in _parse(BASE).devices][-1] == "Hall"


@pytest.mark.parametrize("version", [None, 2, "1", True])
def test_version_must_be_1(version):
    data = _with(lambda d: d.update(version=version) if version is not None else d.pop("version"))
    with pytest.raises(ConfigError, match="version"):
        _parse(data)


def test_devices_must_be_list_of_objects():
    with pytest.raises(ConfigError, match="devices"):
        _parse(_with(lambda d: d.update(devices={"x": 1})))
    with pytest.raises(ConfigError, match="devices"):
        _parse(_with(lambda d: d.update(devices=["x"])))


@pytest.mark.parametrize("field", ["name", "room", "type", "backend", "connection"])
def test_required_device_fields(field):
    data = _with(lambda d: d["devices"][0].pop(field))
    with pytest.raises(ConfigError, match=field):
        _parse(data)


def test_backend_validation_runs():
    data = _with(lambda d: d["devices"][0]["connection"].pop("key"))
    with pytest.raises(ConfigError, match=r"Kitchen left.*connection\.key"):
        _parse(data)


def test_unknown_type_and_backend_are_skipped():
    def add(d):
        d["devices"].append({"name": "Hall light", "room": "Hall", "type": "light", "backend": "zigbee2mqtt",
                             "connection": {"topic": "z2m/hall"}})
        d["devices"].append({"name": "Hall fan", "room": "Hall", "type": "shutter", "backend": "future_lan",
                             "connection": {}})

    cfg = _parse(_with(add))
    assert [d.name for d in cfg.devices] == ["Kitchen left", "Kitchen right", "Hall"]
    assert cfg.skipped == (("Hall light", "unknown type 'light'"), ("Hall fan", "unknown backend 'future_lan'"))


def test_duplicate_device_names_and_aliases_rejected():
    with pytest.raises(ConfigError, match=r"duplicate.*kitchen left"):
        _parse(_with(lambda d: d["devices"][1].update(name="  KITCHEN left ")))
    with pytest.raises(ConfigError, match=r"duplicate.*מטבח שמאל"):
        _parse(_with(lambda d: d["devices"][2].update(aliases=["מטבח שמאל"])))


def test_device_name_colliding_with_other_room_rejected():
    with pytest.raises(ConfigError, match=r"'kitchen'.*room"):
        _parse(_with(lambda d: d["devices"][2].update(aliases=["Kitchen"])))


def test_device_name_equal_to_own_multi_device_room_rejected():
    with pytest.raises(ConfigError, match=r"'kitchen'.*room"):
        _parse(_with(lambda d: d["devices"][0].update(name="Kitchen")))


def test_room_alias_collisions_rejected():
    def mutate(d):
        d["rooms"]["Hall"] = {"aliases": ["המטבח"]}

    with pytest.raises(ConfigError, match=r"duplicate.*המטבח"):
        _parse(_with(mutate))


@pytest.mark.parametrize("where", ["name", "alias", "room", "room_alias"])
def test_reserved_all_rejected(where):
    def mutate(d):
        dev = d["devices"][0]
        if where == "name":
            dev["name"] = "ALL"
        elif where == "alias":
            dev["aliases"] = ["all"]
        elif where == "room":
            dev["room"] = "All"
        else:
            d["rooms"]["Kitchen"]["aliases"] = ["all"]

    with pytest.raises(ConfigError, match="reserved"):
        _parse(_with(mutate))


def test_bad_aliases_and_rooms_types_rejected():
    with pytest.raises(ConfigError, match="aliases"):
        _parse(_with(lambda d: d["devices"][0].update(aliases="x")))
    with pytest.raises(ConfigError, match="rooms"):
        _parse(_with(lambda d: d.update(rooms=["Kitchen"])))
    with pytest.raises(ConfigError, match="options"):
        _parse(_with(lambda d: d["devices"][0].update(options=[1])))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_config.py -q`
Expected: collection error `No module named 'home_control.config'`

- [ ] **Step 3: Implement** `src/home_control/config.py`

```python
"""Validate a version-1 device configuration (already-parsed JSON)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from home_control.backends.base import Backend
from home_control.errors import ConfigError
from home_control.models import SHUTTER, Device, normalize_name

logger = logging.getLogger(__name__)

KNOWN_TYPES = frozenset({SHUTTER})
ALL = "all"
_REQUIRED_STR = ("name", "room", "type", "backend")


@dataclass(frozen=True)
class ParsedConfig:
    """Devices this version can drive, their rooms, and what was skipped."""

    devices: tuple[Device, ...]
    rooms: dict[str, tuple[str, ...]]
    skipped: tuple[tuple[str, str], ...]


def _str_list(raw: Any, where: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
        raise ConfigError(f"{where}: aliases must be a list of strings")
    return tuple(raw)


def _check_not_reserved(value: str, where: str) -> None:
    if normalize_name(value) == ALL:
        raise ConfigError(f"{where}: '{value}' is reserved (it means every device)")


def _parse_rooms(raw: Any) -> dict[str, tuple[str, tuple[str, ...]]]:
    """normalized room key -> (display name, aliases)."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError("rooms must be an object mapping room name to {\"aliases\": [...]}")
    rooms: dict[str, tuple[str, tuple[str, ...]]] = {}
    for name, body in raw.items():
        if not isinstance(body, dict):
            raise ConfigError(f"rooms['{name}'] must be an object")
        _check_not_reserved(name, f"room '{name}'")
        aliases = _str_list(body.get("aliases"), f"room '{name}'")
        for alias in aliases:
            _check_not_reserved(alias, f"room '{name}'")
        rooms[normalize_name(name)] = (name, aliases)
    return rooms


def _parse_device(index: int, raw: Any, rooms: dict[str, tuple[str, tuple[str, ...]]]) -> Device:
    if not isinstance(raw, dict):
        raise ConfigError(f"devices[{index}] must be an object")
    label = raw.get("name") if isinstance(raw.get("name"), str) else f"#{index + 1}"
    where = f"device '{label}'"
    for field in _REQUIRED_STR:
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{where}: missing or empty '{field}'")
    if not isinstance(raw.get("connection"), dict):
        raise ConfigError(f"{where}: 'connection' must be an object")
    options = raw.get("options", {})
    if not isinstance(options, dict):
        raise ConfigError(f"{where}: 'options' must be an object")
    name = raw["name"].strip()
    aliases = _str_list(raw.get("aliases"), where)
    room = raw["room"].strip()
    for value in (name, *aliases, room):
        _check_not_reserved(value, where)
    room = rooms.get(normalize_name(room), (room, ()))[0]
    return Device(
        name=name,
        room=room,
        type=raw["type"].strip(),
        backend=raw["backend"].strip(),
        connection=dict(raw["connection"]),
        aliases=aliases,
        options=dict(options),
    )


def _check_names(devices: list[Device], rooms: dict[str, tuple[str, tuple[str, ...]]]) -> None:
    owner: dict[str, str] = {}
    for d in devices:
        for value in (d.name, *d.aliases):
            key = normalize_name(value)
            if key in owner:
                raise ConfigError(f"duplicate name or alias '{key}' (devices '{owner[key]}' and '{d.name}')")
            owner[key] = d.name
    room_owner: dict[str, str] = {}
    for room_key, (display, aliases) in rooms.items():
        for value in (display, *aliases):
            key = normalize_name(value)
            if key in room_owner and room_owner[key] != display:
                raise ConfigError(f"duplicate room name or alias '{key}' (rooms '{room_owner[key]}' and '{display}')")
            room_owner[key] = display
    members: dict[str, list[Device]] = {}
    for d in devices:
        members.setdefault(normalize_name(d.room), []).append(d)
    for key, device_name in owner.items():
        if key not in room_owner:
            continue
        room = room_owner[key]
        device = next(d for d in devices if d.name == device_name)
        if not (normalize_name(device.room) == normalize_name(room) and len(members[normalize_name(room)]) == 1
                and key == normalize_name(device.name) == normalize_name(room)):
            raise ConfigError(f"name '{key}' of device '{device_name}' is also a room name or alias (room '{room}')")


def parse_config(data: Mapping[str, Any], backends: Mapping[str, Backend]) -> ParsedConfig:
    """Validate a version-1 config and return the devices this version can drive."""
    version = data.get("version")
    if version != 1 or isinstance(version, bool):
        raise ConfigError(f"unsupported config version {version!r} (expected 1)")
    raw_devices = data.get("devices")
    if not isinstance(raw_devices, list):
        raise ConfigError("devices must be a list")
    rooms = _parse_rooms(data.get("rooms"))
    devices: list[Device] = []
    skipped: list[tuple[str, str]] = []
    for i, raw in enumerate(raw_devices):
        device = _parse_device(i, raw, rooms)
        if device.type not in KNOWN_TYPES:
            skipped.append((device.name, f"unknown type '{device.type}'"))
            continue
        backend = backends.get(device.backend)
        if backend is None:
            skipped.append((device.name, f"unknown backend '{device.backend}'"))
            continue
        backend.validate(device)
        devices.append(device)
    for d in devices:
        rooms.setdefault(normalize_name(d.room), (d.room, ()))
    _check_names(devices, rooms)
    for name, reason in skipped:
        logger.warning("skipping device '%s': %s", name, reason)
    used = {normalize_name(d.room) for d in devices}
    return ParsedConfig(
        devices=tuple(devices),
        rooms={display: aliases for key, (display, aliases) in rooms.items() if key in used},
        skipped=tuple(skipped),
    )
```

Add `ParsedConfig`, `parse_config` to `src/home_control/__init__.py` imports and `__all__`.

- [ ] **Step 4: Run all checks**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass; ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: version-1 config schema with forward-compatible skipping

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Home facade

**Files:**
- Create: `src/home_control/home.py`
- Modify: `src/home_control/__init__.py`
- Test: `tests/test_home.py`

**Interfaces:**
- Consumes: `parse_config`, `ParsedConfig`, `ALL` (Task 4); `default_backends`, `Backend`, `BackendError` (Task 3); models/errors (Task 2)
- Produces:
  - `Home(config: ParsedConfig, backends: Mapping[str, Backend])`
  - `Home.from_config(data, backends=None) -> Home`
  - `.devices -> tuple[Device, ...]`
  - `.skipped -> tuple[tuple[str, str], ...]`
  - `.resolve(target) -> list[Device]`
  - `async .move(target, direction) / .up / .down / .stop(target) -> list[CommandResult]` (shutters only)
  - `async .status(target) -> dict[str, dict[str, Any]]`
  - `.valid_names(device_type: str | None = None) -> list[str]`
  - `.names() -> {"devices": [{"name", "room", "type", "aliases"}], "rooms": [{"name", "aliases", "devices"}], "skipped": [{"name", "reason"}]}`

- [ ] **Step 1: Write the failing tests** (`tests/test_home.py`)

```python
import asyncio
from typing import Any

import pytest

from home_control.backends.base import BackendError
from home_control.config import parse_config
from home_control.errors import UnknownTargetError
from home_control.home import Home
from home_control.models import CommandResult, Device, Direction, Outcome


def _dev(name, room, dev_id, aliases=(), dtype="shutter"):
    return {"name": name, "room": room, "type": dtype, "backend": "fake", "aliases": list(aliases),
            "connection": {"id": dev_id}}


CONFIG = {
    "version": 1,
    "rooms": {"Kitchen": {"aliases": ["המטבח"]}, "Kid's room": {"aliases": ["חדר הילדים"]}},
    "devices": [
        _dev("Kitchen left", "Kitchen", "a", aliases=["מטבח שמאל"]),
        _dev("Kitchen right", "Kitchen", "b"),
        _dev("Kid's room", "Kid's room", "c"),
        _dev("Hall left", "Hall", "d"),
        _dev("Hall right", "Hall", "e"),
    ],
}


class FakeBackend:
    def __init__(self, fail=None, raise_for=None):
        self.calls: list[tuple[str, Direction]] = []
        self.fail: dict[str, Outcome] = fail or {}
        self.raise_for: set[str] = raise_for or set()
        self.in_flight = 0
        self.max_in_flight = 0

    def validate(self, device: Device) -> None:
        pass

    async def move(self, device: Device, direction: Direction) -> CommandResult:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        self.calls.append((device.name, direction))
        if device.name in self.raise_for:
            raise RuntimeError("boom")
        outcome = self.fail.get(device.name, Outcome.OK)
        return CommandResult(device.name, outcome, None if outcome is Outcome.OK else "x")

    async def status(self, device: Device) -> dict[str, Any]:
        if device.name in self.fail:
            raise BackendError(self.fail[device.name], "no answer")
        return {"1": "stop"}


def _home(backend=None, config=CONFIG):
    return Home.from_config(config, {"fake": backend or FakeBackend()})


def _names(devices):
    return [d.name for d in devices]


def test_from_config_with_default_backends_skips_fake_backend():
    home = Home.from_config(CONFIG)
    assert home.devices == () and len(home.skipped) == 5


def test_resolve_device_room_all():
    home = _home()
    assert _names(home.resolve("Kitchen left")) == ["Kitchen left"]
    assert _names(home.resolve("Kitchen")) == ["Kitchen left", "Kitchen right"]
    assert _names(home.resolve("hall")) == ["Hall left", "Hall right"]
    assert _names(home.resolve("Kid's room")) == ["Kid's room"]
    assert len(home.resolve("ALL")) == 5


def test_resolve_normalizes_and_accepts_hebrew():
    home = _home()
    assert _names(home.resolve("  KITCHEN ")) == ["Kitchen left", "Kitchen right"]
    assert _names(home.resolve("המטבח")) == ["Kitchen left", "Kitchen right"]
    assert _names(home.resolve("מטבח  שמאל")) == ["Kitchen left"]
    assert _names(home.resolve("Kid’s room")) == ["Kid's room"]
    assert _names(home.resolve("חדר הילדים")) == ["Kid's room"]


def test_unknown_and_empty_targets():
    home = _home()
    with pytest.raises(UnknownTargetError) as exc:
        home.resolve("garage")
    assert exc.value.target == "garage"
    assert {"Kitchen left", "Kitchen", "all"} <= set(exc.value.valid)
    with pytest.raises(UnknownTargetError):
        home.resolve("   ")


async def test_room_runs_concurrently():
    backend = FakeBackend()
    results = await _home(backend).down("Kitchen")
    assert [r.device_name for r in results] == ["Kitchen left", "Kitchen right"]
    assert all(r.ok for r in results) and backend.max_in_flight == 2


async def test_failures_isolated_and_logged(caplog):
    backend = FakeBackend(fail={"Hall left": Outcome.UNREACHABLE}, raise_for={"Kitchen left"})
    with caplog.at_level("WARNING", logger="home_control.home"):
        results = await _home(backend).up("all")
    by_name = {r.device_name: r for r in results}
    assert by_name["Hall left"].outcome is Outcome.UNREACHABLE
    assert by_name["Kitchen left"].outcome is Outcome.REJECTED and "boom" in (by_name["Kitchen left"].detail or "")
    assert sum(r.ok for r in results) == 3
    assert "Hall left" in caplog.text and "home-control scan" in caplog.text
    assert "Hall right" not in caplog.text


async def test_move_ignores_non_shutter_devices():
    config = {"version": 1, "devices": [
        _dev("Hall lamp", "Hall", "x", dtype="shutter"),
        _dev("Porch", "Porch", "y"),
    ]}
    home = _home(config=config)
    # make "Hall lamp" a non-shutter after parsing, as a future type would be
    home._devices = tuple(Device(d.name, d.room, "light" if d.name == "Hall lamp" else d.type, d.backend,
                                 d.connection) for d in home.devices)
    with pytest.raises(UnknownTargetError) as exc:
        await home.down("Hall")
    assert exc.value.valid == ["Porch", "all"]


async def test_status_maps_failures():
    status = await _home(FakeBackend(fail={"Kitchen right": Outcome.UNREACHABLE})).status("Kitchen")
    assert status == {"Kitchen left": {"1": "stop"}, "Kitchen right": {"error": "unreachable: no answer"}}


def test_names_shape():
    config = {**CONFIG, "devices": [*CONFIG["devices"], {**_dev("Hall light", "Hall", "z"), "type": "light"}]}
    names = _home(config=config).names()
    rooms = {r["name"]: r for r in names["rooms"]}
    assert rooms["Kitchen"] == {"name": "Kitchen", "aliases": ["המטבח"], "devices": ["Kitchen left", "Kitchen right"]}
    assert names["devices"][0] == {"name": "Kitchen left", "room": "Kitchen", "type": "shutter", "aliases": ["מטבח שמאל"]}
    assert names["skipped"] == [{"name": "Hall light", "reason": "unknown type 'light'"}]


def test_constructor_accepts_parsed_config():
    backends = {"fake": FakeBackend()}
    home = Home(parse_config(CONFIG, backends), backends)
    assert len(home.devices) == 5
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_home.py -q`
Expected: collection error `No module named 'home_control.home'`

- [ ] **Step 3: Implement** `src/home_control/home.py`

```python
"""Home facade: resolve targets and run commands concurrently."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from home_control.backends import default_backends
from home_control.backends.base import Backend, BackendError
from home_control.config import ALL, ParsedConfig, parse_config
from home_control.errors import UnknownTargetError
from home_control.models import SHUTTER, CommandResult, Device, Direction, Outcome, normalize_name

logger = logging.getLogger(__name__)


class Home:
    """The configured devices, behind their backends."""

    def __init__(self, config: ParsedConfig, backends: Mapping[str, Backend]) -> None:
        self._devices = config.devices
        self._room_aliases = dict(config.rooms)
        self._skipped = config.skipped
        self._backends = dict(backends)

    @classmethod
    def from_config(cls, data: Mapping[str, Any], backends: Mapping[str, Backend] | None = None) -> Home:
        """Validate config data and build a Home. Raises ConfigError."""
        backends = default_backends() if backends is None else backends
        return cls(parse_config(data, backends), backends)

    @property
    def devices(self) -> tuple[Device, ...]:
        """Drivable devices, in config order."""
        return self._devices

    @property
    def skipped(self) -> tuple[tuple[str, str], ...]:
        """Devices this version can't drive: (name, reason)."""
        return self._skipped

    def _rooms(self, devices: tuple[Device, ...] | list[Device]) -> dict[str, list[Device]]:
        rooms: dict[str, list[Device]] = {}
        for d in devices:
            rooms.setdefault(d.room, []).append(d)
        return rooms

    def _match(self, target: str, devices: tuple[Device, ...] | list[Device]) -> list[Device]:
        key = normalize_name(target)
        if key == ALL:
            return list(devices)
        for d in devices:
            if key in {normalize_name(n) for n in (d.name, *d.aliases)}:
                return [d]
        for room, members in self._rooms(devices).items():
            if key in {normalize_name(n) for n in (room, *self._room_aliases.get(room, ()))}:
                return members
        return []

    def resolve(self, target: str) -> list[Device]:
        """Devices a target names: 'all', then a device name/alias, then a room name/alias."""
        found = self._match(target, self._devices)
        if not found:
            raise UnknownTargetError(target, self.valid_names())
        return found

    async def _safe_move(self, device: Device, direction: Direction) -> CommandResult:
        try:
            return await self._backends[device.backend].move(device, direction)
        except Exception as exc:  # a backend bug must not break the other devices
            return CommandResult(device.name, Outcome.REJECTED, f"{type(exc).__name__}: {exc}")

    async def move(self, target: str, direction: Direction) -> list[CommandResult]:
        """Move or stop every shutter the target names, concurrently."""
        shutters = [d for d in self._devices if d.type == SHUTTER]
        found = self._match(target, shutters)
        if not found:
            raise UnknownTargetError(target, self.valid_names(SHUTTER))
        results = list(await asyncio.gather(*(self._safe_move(d, direction) for d in found)))
        for r in results:
            if not r.ok:
                hint = "; if its IP changed, run: home-control scan" if r.outcome is Outcome.UNREACHABLE else ""
                logger.warning("%s %s: %s (%s)%s", direction.value, r.device_name, r.outcome.value, r.detail, hint)
        return results

    async def up(self, target: str) -> list[CommandResult]:
        """Raise the target's shutters."""
        return await self.move(target, Direction.UP)

    async def down(self, target: str) -> list[CommandResult]:
        """Lower the target's shutters."""
        return await self.move(target, Direction.DOWN)

    async def stop(self, target: str) -> list[CommandResult]:
        """Stop the target's shutters."""
        return await self.move(target, Direction.STOP)

    async def _safe_status(self, device: Device) -> dict[str, Any]:
        try:
            return await self._backends[device.backend].status(device)
        except BackendError as exc:
            return {"error": f"{exc.outcome.value}: {exc.detail}"}
        except Exception as exc:
            return {"error": f"{Outcome.REJECTED.value}: {type(exc).__name__}: {exc}"}

    async def status(self, target: str) -> dict[str, dict[str, Any]]:
        """Raw state (or an error) per device."""
        devices = self.resolve(target)
        values = await asyncio.gather(*(self._safe_status(d) for d in devices))
        return {d.name: v for d, v in zip(devices, values)}

    def valid_names(self, device_type: str | None = None) -> list[str]:
        """Device names, then room names (deduplicated), then 'all' — optionally for one device type."""
        devices = [d for d in self._devices if device_type is None or d.type == device_type]
        names = [d.name for d in devices]
        names += [room for room in self._rooms(devices) if room not in names]
        return [*names, ALL]

    def names(self) -> dict[str, Any]:
        """Devices, rooms and skipped devices, for listing."""
        return {
            "devices": [{"name": d.name, "room": d.room, "type": d.type, "aliases": list(d.aliases)} for d in self._devices],
            "rooms": [
                {"name": room, "aliases": list(self._room_aliases.get(room, ())), "devices": [m.name for m in members]}
                for room, members in self._rooms(self._devices).items()
            ],
            "skipped": [{"name": name, "reason": reason} for name, reason in self._skipped],
        }
```

Add `Home` to `src/home_control/__init__.py` imports and `__all__`.

- [ ] **Step 4: Run all checks**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass; ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Home facade built from config data

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: CLI

**Files:**
- Create: `src/home_control/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes:
  - `load_config_file`, `save_config_file` (Task 2)
  - `parse_config` (Task 4)
  - `default_backends` (Task 3)
  - `Home` (Task 5)
  - `ConfigError`, `UnknownTargetError`
- Produces:
  - `main(argv: Sequence[str] | None = None) -> int`
  - Module hooks (patched in tests): `_backends() -> dict[str, Backend]`, `_scan() -> dict[str, dict[str, Any]]`
- Exit codes: 0 ok; 1 some device failed, wasn't found, or returned an error; 2 config or usage error.

- [ ] **Step 1: Write the failing tests** (`tests/test_cli.py`)

```python
import json
from pathlib import Path
from typing import Any

import pytest

from home_control import cli
from home_control.files import load_config_file, save_config_file
from home_control.models import CommandResult, Device, Direction, Outcome

CONFIG = {
    "version": 1,
    "rooms": {"Kitchen": {"aliases": ["המטבח"]}},
    "devices": [
        {"name": "Kitchen left", "room": "Kitchen", "type": "shutter", "backend": "tuya_lan",
         "connection": {"id": "dev-a", "ip": "192.0.2.10", "key": "0123456789abcdef"}},
        {"name": "Kitchen right", "room": "Kitchen", "type": "shutter", "backend": "tuya_lan",
         "connection": {"id": "dev-b", "ip": "192.0.2.11", "key": "0123456789abcdef", "version": 3.3},
         "options": {"inverted": True, "future_option": 7}},
        {"name": "Hall light", "room": "Hall", "type": "light", "backend": "zigbee2mqtt", "connection": {"topic": "t"}},
    ],
}


class FakeBackend:
    def __init__(self):
        self.fail: set[str] = set()
        self.status_fail: set[str] = set()
        self.calls: list[tuple[str, Direction]] = []

    def validate(self, device: Device) -> None:
        pass

    async def move(self, device: Device, direction: Direction) -> CommandResult:
        self.calls.append((device.name, direction))
        if device.name in self.fail:
            return CommandResult(device.name, Outcome.UNREACHABLE, "timeout")
        return CommandResult(device.name, Outcome.OK)

    async def status(self, device: Device) -> dict[str, Any]:
        if device.name in self.status_fail:
            from home_control.backends.base import BackendError

            raise BackendError(Outcome.UNREACHABLE, "timeout")
        return {"1": "stop"}


@pytest.fixture
def cfg(tmp_path: Path) -> Path:
    path = tmp_path / "home.json"
    save_config_file(path, CONFIG)
    return path


@pytest.fixture
def backend(monkeypatch) -> FakeBackend:
    fake = FakeBackend()
    monkeypatch.setattr(cli, "_backends", lambda: {"tuya_lan": fake})
    return fake


def test_up_room(cfg, backend, capsys):
    assert cli.main(["--config", str(cfg), "up", "Kitchen"]) == 0
    out = capsys.readouterr().out
    assert "Kitchen left: ok" in out and "Kitchen right: ok" in out


def test_env_var_and_multiword_target(cfg, backend, monkeypatch):
    monkeypatch.setenv("HOME_CONTROL_CONFIG", str(cfg))
    assert cli.main(["down", "Kitchen", "left"]) == 0
    assert backend.calls == [("Kitchen left", Direction.DOWN)]


def test_no_config_is_usage_error(monkeypatch, capsys):
    monkeypatch.delenv("HOME_CONTROL_CONFIG", raising=False)
    assert cli.main(["list"]) == 2
    assert "--config" in capsys.readouterr().err


def test_missing_file_is_usage_error(tmp_path, capsys):
    assert cli.main(["--config", str(tmp_path / "nope.json"), "list"]) == 2
    err = capsys.readouterr().err
    assert "file not found" in err and "import" in err


def test_failure_exit_1(cfg, backend, capsys):
    backend.fail = {"Kitchen right"}
    assert cli.main(["--config", str(cfg), "stop", "all"]) == 1
    assert "Kitchen right: unreachable (timeout)" in capsys.readouterr().out


def test_unknown_target_exit_2(cfg, backend, capsys):
    assert cli.main(["--config", str(cfg), "up", "garage"]) == 2
    assert "unknown target 'garage'" in capsys.readouterr().err


def test_list_includes_skipped(cfg, backend, capsys):
    assert cli.main(["--config", str(cfg), "list"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["rooms"][0]["devices"] == ["Kitchen left", "Kitchen right"]
    assert data["skipped"] == [{"name": "Hall light", "reason": "unknown type 'light'"}]


def test_status_exit_1_on_error(cfg, backend, capsys):
    assert cli.main(["--config", str(cfg), "status", "Kitchen left"]) == 0
    assert json.loads(capsys.readouterr().out) == {"Kitchen left": {"1": "stop"}}
    backend.status_fail = {"Kitchen right"}
    assert cli.main(["--config", str(cfg), "status", "Kitchen"]) == 1


EXPORT = [
    {"id": "dev-a", "name": "Tuya name A", "key": "0123456789abcdef", "ip": "192.0.2.10", "version": "3.3"},
    {"id": "dev-b", "name": "Tuya name B", "key": "0123456789abcdef", "ip": "192.0.2.11", "version": "3.3"},
]


def _answers(monkeypatch, answers):
    prompts = []
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or next(it))
    return prompts


def test_import_writes_v1(tmp_path, monkeypatch):
    export = tmp_path / "devices.json"
    export.write_text(json.dumps(EXPORT), encoding="utf-8")
    out = tmp_path / "home.json"
    prompts = _answers(monkeypatch, ["Kitchen left", "Kitchen", "מטבח שמאל", "המטבח", "", "Kitchen", ""])
    assert cli.main(["--config", str(out), "import", str(export)]) == 0
    data = load_config_file(out)
    assert data["version"] == 1
    assert data["rooms"] == {"Kitchen": {"aliases": ["המטבח"]}}
    assert [d["name"] for d in data["devices"]] == ["Kitchen left", "Tuya name B"]
    assert data["devices"][0] == {
        "name": "Kitchen left", "aliases": ["מטבח שמאל"], "room": "Kitchen", "type": "shutter", "backend": "tuya_lan",
        "connection": {"id": "dev-a", "ip": "192.0.2.10", "key": "0123456789abcdef", "version": 3.3},
    }
    assert sum("Room aliases" in p for p in prompts) == 1


def test_import_refuses_overwrite_and_invalid_result(cfg, tmp_path, monkeypatch, capsys):
    export = tmp_path / "devices.json"
    export.write_text(json.dumps(EXPORT), encoding="utf-8")
    assert cli.main(["--config", str(cfg), "import", str(export)]) == 2
    assert "--force" in capsys.readouterr().err
    out = tmp_path / "new.json"
    _answers(monkeypatch, ["Same", "Kitchen", "", "", "same", "Kitchen", ""])
    assert cli.main(["--config", str(out), "import", str(export)]) == 2
    assert "duplicate" in capsys.readouterr().err and not out.exists()


def test_import_bad_json_is_usage_error(tmp_path, capsys):
    export = tmp_path / "devices.json"
    export.write_text("{nope", encoding="utf-8")
    assert cli.main(["--config", str(tmp_path / "o.json"), "import", str(export)]) == 2


def test_scan_updates_only_ips_and_preserves_unknown_fields(cfg, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_scan", lambda: {"dev-a": {"ip": "192.0.2.50"}, "dev-b": {"ip": "192.0.2.11"}})
    assert cli.main(["--config", str(cfg), "scan"]) == 0
    assert "Kitchen left: 192.0.2.10 -> 192.0.2.50" in capsys.readouterr().out
    expected = json.loads(json.dumps(CONFIG))
    expected["devices"][0]["connection"]["ip"] = "192.0.2.50"
    assert load_config_file(cfg) == expected


test_scan_preserves_unknown_fields = test_scan_updates_only_ips_and_preserves_unknown_fields


def test_scan_missing_device_exit_1(cfg, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_scan", lambda: {"dev-a": {"ip": "192.0.2.10"}})
    assert cli.main(["--config", str(cfg), "scan"]) == 1
    assert "Kitchen right: not found on the LAN" in capsys.readouterr().out
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_cli.py -q`
Expected: collection error `cannot import name 'cli'`

- [ ] **Step 3: Implement** `src/home_control/cli.py`

```python
"""home-control command line."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import tinytuya

from home_control.backends import default_backends
from home_control.backends.base import Backend
from home_control.config import parse_config
from home_control.errors import ConfigError, UnknownTargetError
from home_control.files import load_config_file, save_config_file
from home_control.home import Home
from home_control.models import Direction

ENV_VAR = "HOME_CONTROL_CONFIG"


def _backends() -> dict[str, Backend]:
    return default_backends()


def _scan() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = tinytuya.deviceScan(verbose=False, poll=False, byID=True)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="home-control", description="Local-only home device control.")
    parser.add_argument("--config", type=Path, help=f"device file (JSON); default ${ENV_VAR}")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("up", "down", "stop", "status"):
        sub.add_parser(name).add_argument("target", nargs="+", help="device, room, or 'all'")
    sub.add_parser("list")
    imp = sub.add_parser("import", help="create the device file from a tinytuya devices.json export (shutters)")
    imp.add_argument("source", type=Path)
    imp.add_argument("--force", action="store_true")
    sub.add_parser("scan", help="find tuya_lan devices on the LAN and update changed IPs")
    return parser


def _split(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _cmd_import(target: Path, source: Path, force: bool) -> int:
    if target.exists() and not force:
        print(f"{target} already exists; pass --force to overwrite", file=sys.stderr)
        return 2
    exported = json.loads(source.read_text(encoding="utf-8"))
    rooms: dict[str, dict[str, list[str]]] = {}
    devices: list[dict[str, Any]] = []
    for dev in exported:
        tuya_name = str(dev.get("name") or dev["id"])
        name = input(f"Name [{tuya_name}]: ").strip() or tuya_name
        room = input("Room: ").strip()
        aliases = _split(input("Aliases (comma-separated, optional): "))
        if room not in rooms:
            rooms[room] = {"aliases": _split(input("Room aliases (comma-separated, optional): "))}
        device: dict[str, Any] = {"name": name}
        if aliases:
            device["aliases"] = aliases
        device.update(room=room, type="shutter", backend="tuya_lan", connection={
            "id": str(dev["id"]), "ip": str(dev["ip"]), "key": str(dev["key"]), "version": float(dev.get("version") or 3.3),
        })
        devices.append(device)
    data = {"version": 1, "rooms": {r: body for r, body in rooms.items() if body["aliases"]}, "devices": devices}
    parse_config(data, _backends())  # validate before writing
    save_config_file(target, data)
    print(f"saved {len(devices)} device(s) to {target}")
    return 0


def _cmd_scan(path: Path) -> int:
    data = load_config_file(path)
    parse_config(data, _backends())
    found = _scan()
    missing = changed = False
    for dev in data["devices"]:
        if dev.get("backend") != "tuya_lan":
            continue
        conn = dev["connection"]
        ip = found.get(conn.get("id"), {}).get("ip")
        if not ip:
            print(f"{dev['name']}: not found on the LAN")
            missing = True
        elif ip != conn.get("ip"):
            print(f"{dev['name']}: {conn.get('ip')} -> {ip}")
            conn["ip"] = ip
            changed = True
        else:
            print(f"{dev['name']}: {ip} (unchanged)")
    if changed:
        save_config_file(path, data)
    return 1 if missing else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; returns the exit code."""
    args = _parser().parse_args(argv)
    env = os.environ.get(ENV_VAR)
    path = args.config or (Path(env).expanduser() if env else None)
    if path is None:
        print(f"no device file: pass --config PATH or set {ENV_VAR}", file=sys.stderr)
        return 2
    try:
        if args.command == "import":
            return _cmd_import(path, args.source, args.force)
        if args.command == "scan":
            return _cmd_scan(path)
        home = Home.from_config(load_config_file(path), _backends())
        if args.command == "list":
            print(json.dumps(home.names(), ensure_ascii=False, indent=2))
            return 0
        target = " ".join(args.target)
        if args.command == "status":
            status = asyncio.run(home.status(target))
            print(json.dumps(status, ensure_ascii=False, indent=2))
            return 1 if any("error" in v for v in status.values()) else 0
        results = asyncio.run(home.move(target, Direction(args.command)))
    except FileNotFoundError as exc:
        print(f"file not found: {exc.filename}; create the device file with: home-control --config PATH import <devices.json>", file=sys.stderr)
        return 2
    except (ConfigError, UnknownTargetError, json.JSONDecodeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for r in results:
        print(f"{r.device_name}: {r.outcome.value}" + (f" ({r.detail})" if r.detail else ""))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run all checks**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass; ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: CLI with explicit --config, import, scan

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Release workflow, new public repo, v0.2.0

**Files:**
- Create: `.github/workflows/release.yml`
- Test: the workflow run itself, and a wheel install check

**Interfaces:**
- Produces: the public repo `aGallea/home-control` with `main`, tag `v0.2.0`, and Release `v0.2.0` with `home_control-0.2.0-py3-none-any.whl` and `home_control-0.2.0.tar.gz`.

- [ ] **Step 1: Write** `.github/workflows/release.yml`

```yaml
name: release
on:
  push:
    tags: ["v*"]
permissions:
  contents: write
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run pytest -q
      - name: Check tag matches version
        run: test "v$(uv run python -c 'import tomllib;print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')" = "$GITHUB_REF_NAME"
      - run: uv build
      - run: gh release create "$GITHUB_REF_NAME" dist/* --title "$GITHUB_REF_NAME" --notes "home-control $GITHUB_REF_NAME"
        env:
          GH_TOKEN: ${{ github.token }}
```

- [ ] **Step 2: Local build check**

Run: `uv build && ls dist && unzip -l dist/home_control-0.2.0-py3-none-any.whl | grep -c home_control/`
Expected: `home_control-0.2.0-py3-none-any.whl` and `home_control-0.2.0.tar.gz` exist; the wheel contains the package files. Then remove `dist/`.

- [ ] **Step 3: Commit, then run the privacy checks**

```bash
git add -A && git commit -m "ci: release workflow builds wheel and sdist on v* tags

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
uv run pytest tests/test_privacy.py -q
python3 scripts/check_no_private_data.py --also "$OWNER_EMAIL" "$TINYTUYA_DEVICES_JSON" "$CURRENT_DEVICES_AS_JSON"
```

Expected: privacy tests pass; the check prints `clean`. On any hit, fix the commit (rewrite this new local history) before going on.

- [ ] **Step 4: Replace the GitHub repo** (approved by the user: delete and recreate)

```bash
gh repo delete aGallea/home-control --yes
gh repo create aGallea/home-control --public --description "Local-only control of home devices (Tuya LAN), configured by the caller" --source . --remote origin
git push -u origin main
```

If `gh repo delete` fails for lack of the `delete_repo` scope, stop and ask the user to run `gh auth refresh -h github.com -s delete_repo`.

- [ ] **Step 5: Tag and verify the release**

```bash
git tag v0.2.0 && git push origin v0.2.0
gh run watch --exit-status "$(gh run list --workflow release --limit 1 --json databaseId -q '.[0].databaseId')"
gh release view v0.2.0 --json assets -q '.assets[].name'
python3 -m venv "$SCRATCH/wheelcheck" && "$SCRATCH/wheelcheck/bin/pip" install -q "home-control @ https://github.com/aGallea/home-control/releases/download/v0.2.0/home_control-0.2.0-py3-none-any.whl" && "$SCRATCH/wheelcheck/bin/home-control" --help | head -1
```

Expected: the CI and release runs succeed; the release has both assets; the wheel installs from the URL and `home-control --help` prints usage.

---

### Task 8: lychee — dependency, robot helper, install script

**Files:**
- Modify: `$LYCHEE/pyproject.toml`, `$LYCHEE/scripts/deps_without.py`, `$LYCHEE/scripts/install_on_robot.sh`
- Test: `$LYCHEE/tests/test_deps_without.py`; update `$LYCHEE/tests/home/test_wiring.py::test_robot_install_ships_home_control`

**Interfaces:**
- Consumes: the release URL (Task 7)
- Produces: lychee installs `home-control==0.2.0` from the release, and the robot install resolves it from the URL.

- [ ] **Step 1: Write the failing tests**

`$LYCHEE/tests/test_deps_without.py`:

```python
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "deps_without.py"


def _load():
    spec = importlib.util.spec_from_file_location("deps_without", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_helper_keeps_direct_url(monkeypatch, capsys):
    mod = _load()
    url = "https://example.invalid/pkg-1.0-py3-none-any.whl"
    monkeypatch.setattr(mod.md, "requires", lambda dist: [f"pkg @ {url}", "httpx>=0.28", "skipme==1"])
    monkeypatch.setattr("sys.argv", ["deps_without.py", "x", "--exclude", "skipme"])
    mod.main()
    assert capsys.readouterr().out.splitlines() == [f"pkg @ {url}", "httpx>=0.28"]
```

In `$LYCHEE/tests/home/test_wiring.py`, replace `test_robot_install_ships_home_control` with:

```python
def test_robot_install_uses_release_not_rsync():
    script = (REPO / "reachy_lychee" / "scripts" / "install_on_robot.sh").read_text()
    assert "home_control" not in script and "home-control" not in script
    pyproject = (REPO / "reachy_lychee" / "pyproject.toml").read_text()
    assert "home-control @ https://github.com/aGallea/home-control/releases/download/v0.2.0/" in pyproject
    assert "[tool.uv.sources]" not in pyproject
```

- [ ] **Step 2: Run to verify failure**

Run: `cd $LYCHEE && uv run pytest tests/test_deps_without.py tests/home/test_wiring.py -q`
Expected: `test_helper_keeps_direct_url` FAILS (the URL is dropped, so it prints `pkg`); `test_robot_install_uses_release_not_rsync` FAILS.

- [ ] **Step 3: Implement**
  1. In `deps_without.py`, replace the final `print(...)` with:
     ```python
             print(f"{req.name}{extra} @ {req.url}" if req.url else f"{req.name}{extra}{req.specifier}")
     ```
  2. In `pyproject.toml`:
     - replace `"home-control",` with `"home-control @ https://github.com/aGallea/home-control/releases/download/v0.2.0/home_control-0.2.0-py3-none-any.whl",`;
     - delete the `[tool.uv.sources]` table (both lines) and the `"home-control" = false` line;
     - change the comment above it to `# Home control (shutters over Tuya LAN), pinned GitHub release`.
  3. In `install_on_robot.sh`, revert to the pre-home-control form:
     - delete the `HOME_CONTROL_DIR=` line and the home-control rsync block (the `echo` line and the two-line `rsync` command);
     - change the pip line back to `"$PIP" install --no-deps "pipecat-ai==$PIPECAT_VERSION" /tmp/reachy_lychee`;
     - change the helper lines back to the single `  "$PY" "$HELPER" reachy-lychee --exclude pipecat-ai,onnxruntime`;
     - change the echo back to `==> pipecat-ai==$PIPECAT_VERSION and reachy_lychee (no deps)`.
  4. Run `cd $LYCHEE && uv sync` and confirm with `uv pip show home-control | head -2` (`Version: 0.2.0`).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_deps_without.py tests/home/test_wiring.py::test_robot_install_uses_release_not_rsync -q && bash -n scripts/install_on_robot.sh && uv run ruff check scripts/deps_without.py`
Expected: pass. The rest of `tests/home` and `tests/tools/test_home.py` use the phase-1 API (`Shutter`, `save_shutters`) and fail until Task 9 rewrites them. Don't run them here.

- [ ] **Step 5: Commit**

```bash
cd $APPS && git add reachy_lychee/pyproject.toml reachy_lychee/scripts reachy_lychee/tests/test_deps_without.py reachy_lychee/tests/home/test_wiring.py
git commit -m "build(lychee): depend on home-control v0.2.0 release wheel; robot helper keeps direct URLs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: lychee — own `home.json`, adapt to the new API

**Files:**
- Modify: `$LYCHEE/src/reachy_lychee/main.py` (`build_home`, plus the call site `home=build_home()` → `home=build_home(instance_path)`), `$LYCHEE/src/reachy_lychee/tools/home.py`, `$LYCHEE/README.md`
- Test: `$LYCHEE/tests/home/test_wiring.py`, `$LYCHEE/tests/tools/test_home.py`

**Interfaces:**
- Consumes: `home_control.Home.from_config`, `load_config_file`, `ConfigError`, `CommandResult.device_name`, `UnknownTargetError` (v0.2.0)
- Produces:
  - `HOME_CONFIG_FILENAME = "home.json"`, `HOME_CONFIG_ENV = "LYCHEE_HOME_CONFIG"`
  - `home_config_path(instance_path: str | Path | None) -> Path`
  - `build_home(instance_path: str | Path | None, path: Path | None = None) -> Any`

- [ ] **Step 1: Write the failing tests.** Replace `$LYCHEE/tests/home/test_wiring.py` with:

```python
from pathlib import Path

from home_control import Home, save_config_file


REPO = Path(__file__).resolve().parents[3]

CONFIG = {
    "version": 1,
    "devices": [
        {"name": "Kitchen left", "room": "Kitchen", "type": "shutter", "backend": "tuya_lan",
         "connection": {"id": "dev-a", "ip": "192.0.2.10", "key": "0123456789abcdef"}},
    ],
}


def test_home_config_path_rules(tmp_path, monkeypatch):
    from reachy_lychee.main import home_config_path

    monkeypatch.delenv("LYCHEE_HOME_CONFIG", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert home_config_path(tmp_path / "inst") == tmp_path / "inst" / "home.json"
    assert home_config_path(None) == tmp_path / "xdg" / "reachy_lychee" / "home.json"
    monkeypatch.setenv("LYCHEE_HOME_CONFIG", str(tmp_path / "custom.json"))
    assert home_config_path(tmp_path / "inst") == tmp_path / "custom.json"


def test_build_home_none_without_config(tmp_path):
    from reachy_lychee.main import build_home

    assert build_home(None, tmp_path / "missing.json") is None


def test_build_home_none_with_invalid_config(tmp_path, caplog):
    from reachy_lychee.main import build_home

    path = tmp_path / "home.json"
    save_config_file(path, {"version": 2, "devices": []})
    assert build_home(None, path) is None
    assert "Home control disabled" in caplog.text


def test_build_home_loads_devices_from_instance_path(tmp_path, monkeypatch):
    from reachy_lychee.main import build_home

    monkeypatch.delenv("LYCHEE_HOME_CONFIG", raising=False)
    save_config_file(tmp_path / "home.json", CONFIG)
    home = build_home(tmp_path)
    assert isinstance(home, Home)
    assert [d.name for d in home.devices] == ["Kitchen left"]


def test_build_home_logs_skipped_devices(tmp_path, caplog):
    from reachy_lychee.main import build_home

    path = tmp_path / "home.json"
    future = {**CONFIG, "devices": [*CONFIG["devices"], {"name": "Hall light", "room": "Hall", "type": "light",
                                                         "backend": "zigbee2mqtt", "connection": {}}]}
    save_config_file(path, future)
    home = build_home(None, path)
    assert [d.name for d in home.devices] == ["Kitchen left"]
    assert "Hall light" in caplog.text and "unknown type 'light'" in caplog.text


def test_build_home_never_raises(tmp_path, monkeypatch, caplog):
    import home_control

    from reachy_lychee.main import build_home

    def boom(path):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(home_control, "load_config_file", boom)
    assert build_home(None, tmp_path / "home.json") is None
    assert "Home control disabled" in caplog.text


def test_main_passes_home_to_deps():
    src = (REPO / "reachy_lychee" / "src" / "reachy_lychee" / "main.py").read_text()
    assert "home=build_home(instance_path)" in src


def test_tool_dependencies_has_home_field():
    from unittest.mock import MagicMock

    from reachy_lychee.tools.core_tools import ToolDependencies
    from reachy_lychee.tools.background_tool_manager import ToolCallRoutine

    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())
    assert deps.home is None
    assert ToolCallRoutine(tool_name="idle_do_nothing", args_json_str="{}", deps=deps).deps is deps


def test_robot_install_uses_release_not_rsync():
    script = (REPO / "reachy_lychee" / "scripts" / "install_on_robot.sh").read_text()
    assert "home_control" not in script and "home-control" not in script
    pyproject = (REPO / "reachy_lychee" / "pyproject.toml").read_text()
    assert "home-control @ https://github.com/aGallea/home-control/releases/download/v0.2.0/" in pyproject
    assert "[tool.uv.sources]" not in pyproject


def test_companion_figure_enables_home():
    lines = (REPO / "reachy_profiles" / "companion" / "tools.txt").read_text().split()
    assert "home" in lines
```

In `$LYCHEE/tests/tools/test_home.py`:
- change `CommandResult("X", …)` uses so the first argument is still a positional `device_name`. Positional use is unchanged, so this needs no edit, but check it.
- change `home.names = MagicMock(return_value={"shutters": [], "rooms": []})` to `{"devices": [], "rooms": [], "skipped": []}`;
- change the `list` expectation in `test_status_and_list` to `{"devices": [], "rooms": [], "skipped": []}`.

- [ ] **Step 2: Run to verify failure**

Run: `cd $LYCHEE && uv run pytest tests/home tests/tools/test_home.py -q`
Expected: failures with `cannot import name 'home_config_path'` and in `build_home` (it calls `load_shutters`, which no longer exists in v0.2.0).

- [ ] **Step 3: Implement.** In `main.py`, replace the whole `build_home` function with:

```python
HOME_CONFIG_FILENAME = "home.json"
HOME_CONFIG_ENV = "LYCHEE_HOME_CONFIG"


def home_config_path(instance_path: str | Path | None) -> Path:
    """Where lychee keeps its home-control device file (same rule as the Apple TV store; env overrides)."""
    override = os.getenv(HOME_CONFIG_ENV)
    if override:
        return Path(override).expanduser()
    if instance_path is not None:
        return Path(instance_path).expanduser() / HOME_CONFIG_FILENAME
    data_home = os.getenv("XDG_DATA_HOME")
    data_root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return data_root / "reachy_lychee" / HOME_CONFIG_FILENAME


def build_home(instance_path: str | Path | None, path: Path | None = None) -> Any:
    """Create the home_control.Home from lychee's home.json; None if not configured (the tool then says so)."""
    log = logging.getLogger(__name__)
    path = path or home_config_path(instance_path)
    try:
        import home_control

        home = home_control.Home.from_config(home_control.load_config_file(path))
    except FileNotFoundError:
        log.info("Home control disabled: no device file at %s", path)
        return None
    except Exception as e:  # ConfigError, ImportError, or anything unexpected: never stop the app from starting
        log.warning("Home control disabled: %s: %s", type(e).__name__, e)
        return None
    # skipped devices are already logged as warnings by home_control.config
    log.info("Home control: %d device(s) from %s", len(home.devices), path)
    return home
```

- Make sure `import os` is present in `main.py`; add it if missing.
- Change `home=build_home(),` to `home=build_home(instance_path),`.

In `tools/home.py`, change both `r.shutter_name` to `r.device_name`.

In `$LYCHEE/README.md`, add a section:

````markdown
## Home control (shutters)

The `home` tool controls window shutters over the LAN via [home-control](https://github.com/aGallea/home-control).
Lychee reads its device file from `<instance path>/home.json` (or `~/.local/share/reachy_lychee/home.json`;
override with `LYCHEE_HOME_CONFIG`). The file holds local keys: keep it `chmod 600` and never commit it.
Create it with `home-control --config <that path> import <tinytuya devices.json>`. To work on home-control
itself, install your checkout over the release: `uv pip install -e ../../../home-control`.
````

- [ ] **Step 4: Run tests and lint**

Run:

```bash
uv run pytest -q
uv run ruff check src/reachy_lychee/main.py src/reachy_lychee/tools/home.py
uv run mypy 2>&1 | grep -E "main.py|tools/home.py"
```

Expected: the full suite is green (compared with the previous 811, the count goes up by the new wiring tests). Ruff is clean on the touched files, and mypy reports no lines for them.

- [ ] **Step 5: Commit**

```bash
cd $APPS && git add reachy_lychee/src/reachy_lychee/main.py reachy_lychee/src/reachy_lychee/tools/home.py reachy_lychee/README.md reachy_lychee/tests/home/test_wiring.py reachy_lychee/tests/tools/test_home.py
git commit -m "feat(lychee): own home.json and build Home from config data (home-control v0.2.0)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Migration, hardware check, PRs

No new code. Some steps touch real devices or GitHub; follow each step's own instructions.

- [ ] **Step 1: Migrate the device file (one-off, nothing committed).**
  1. With a short script in `$SCRATCH`, convert the old TOML device file to the v1 schema:
     - each `[[shutter]]` becomes a device: `name`, `aliases`, `room`, `type: "shutter"`, `backend: "tuya_lan"`, `connection: {id, ip, key, version}`, and `options: {"inverted": true}` only if it was set;
     - room aliases move to the top-level `rooms`.
  2. Write the result to `home_config_path(None)` with `save_config_file` (mode 600).
  3. Check it with `home-control --config <that path> list`.
  4. Delete the old TOML file and its now-empty folder.
- [ ] **Step 2: Hardware check (user watching).**
  1. Run `home-control --config <path> status all`. Expected: all devices answer.
  2. Restart lychee in the simulator (`.venv/bin/reachy-lychee --ui`). Expected log: `Home control: N device(s) from …/home.json`.
  3. The user gives one voice command (down, then stop) on one room and confirms the shutters moved.
- [ ] **Step 3: Update PRs.**
  1. Push `feat/lychee-home-shutters` and edit the PR body: it now depends on the home-control v0.2.0 release; there's no rsync; the device file lives in lychee's data folder.
  2. Rerun the privacy check against the home-control history before any further push to that repo.
