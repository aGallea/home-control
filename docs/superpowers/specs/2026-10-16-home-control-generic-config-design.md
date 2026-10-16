# home-control: generic config and GitHub-hosted package — Design

**Date:** 2026-10-16
**Status:** Draft, awaiting review
**Supersedes:** the phase-1 shutters design (removed from this repo; it contained device data).

## Goal

Make `home-control` a generic, config-agnostic library that holds **no** device information (no IDs, IPs, keys, names or rooms, in code, docs, or tests). The application using it owns the device file and passes its contents in. New switches, and later new kinds of devices, are added by editing that file, not by changing the library. The library is distributed as a versioned wheel on GitHub Releases, so consumers stop depending on a relative path.

## Principles

- **No device data in this repo.** Examples and tests use made-up devices ("Kitchen left", id `dev-kitchen-left`, IPs from `192.0.2.0/24`, the documentation range).
- **The caller owns the location.** The library never picks a default path. Helpers read and write a file at a path they are given.
- **Forward-compatible schema.** A device whose `type` or `backend` this version doesn't know is skipped with a warning, never fatal. A newer device file keeps working, in part, on an older install.
- **No cloud.** Unchanged: LAN-only backends.

## Privacy (public repo)

The repo is public, so it must contain no private data or information.

**Never in the repo**, in any file, commit message, PR text or release note:
- device IDs, local keys or real IPs;
- home layout, room names or people's names;
- the owner's email address.

**Commit identity:** commits use the GitHub no-reply address `5315995+aGallea@users.noreply.github.com`, set in this repo's local git config.

**Automated guard:** a test (`tests/test_privacy.py`, also run in CI) fails if any tracked file contains:
- a private-range IPv4 address (`10.x`, `172.16–31.x`, `192.168.x`);
- an email address other than the no-reply one.

Examples use `192.0.2.0/24` (TEST-NET-1).

**Pre-push check:**
- Before every push, a local script compares the outgoing commits (content, messages and author emails) against a deny-list built from the owner's real device files. Those files live outside the repo, e.g. a tinytuya `devices.json` and lychee's `home.json`.
- The script is `scripts/check_no_private_data.sh`. It takes the deny-list file paths as arguments, so the repo itself never contains them.
- Release notes are reviewed with the same rule.

## Config schema (version 1)

The file is JSON. Example:

```json
{
  "version": 1,
  "rooms": {
    "Kitchen": {"aliases": ["המטבח"]}
  },
  "devices": [
    {
      "name": "Kitchen left",
      "aliases": ["מטבח שמאל"],
      "room": "Kitchen",
      "type": "shutter",
      "backend": "tuya_lan",
      "connection": {"id": "dev-kitchen-left", "ip": "192.0.2.10", "key": "0123456789abcdef", "version": 3.3},
      "options": {"inverted": false}
    }
  ]
}
```

**Top level:**
- `version`: integer, required; must be `1`.
- `devices`: list, required, may be empty.
- `rooms`: object, optional; maps a room name to `{"aliases": [str]}`.

**Device fields:**

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Display name; unique across all devices and their aliases |
| `aliases` | no | Extra names (e.g. Hebrew) |
| `room` | yes | Room name; needn't appear in `rooms` (then it has no aliases) |
| `type` | yes | Capability. Known in this version: `shutter` |
| `backend` | yes | How to reach the device. Known in this version: `tuya_lan` |
| `connection` | yes | Backend-specific object, validated by that backend |
| `options` | no | Type/backend-specific object, validated by that backend |

**`tuya_lan` backend:**
- `connection`: `id` (str), `ip` (str), `key` (str) required; `version` (number, default `3.3`).
- `options`: `inverted` (bool, default `false`).

**Validation** (raises `ConfigError`, naming the device and field):
- required fields are present and of the right type;
- `connection` and `options` pass the backend's own check;
- names and aliases of devices, and names and aliases of rooms, are unique after normalization;
- a device name may equal its own room's name when it is that room's only device (e.g. a one-shutter room);
- the reserved name `all` is rejected as a device name, room name or alias.

**Unknown `type` or `backend`:** the device is skipped and recorded in `Home.skipped` (name and reason), and a warning is logged.

## Library API

```python
from home_control import Home, ConfigError, UnknownTargetError, load_config_file, save_config_file

data = load_config_file(path)   # JSON → dict; ConfigError if unreadable, invalid JSON, or group/other-readable
home = Home.from_config(data)   # validate and build; ConfigError on invalid data
await home.up("Kitchen")        # -> list[CommandResult]; also down / stop
await home.status("all")        # -> dict[name, dps | {"error": ...}]
home.names()                    # {"devices": [...], "rooms": [...]}
home.skipped                    # [(name, reason)], devices this version can't drive
save_config_file(path, data)    # atomic write, mode 600
```

- `Home.from_config` accepts the dict, so a caller can read it from anywhere (file, env var, test fixture).
- File helpers are separate and take an explicit path. A missing file raises `FileNotFoundError`, so callers can treat "not configured" separately from "broken".
- **Model:** `Device` is a frozen dataclass with `name`, `room`, `type`, `backend`, `aliases`, `connection`, `options`. `connection` and `options` are excluded from `repr`, so keys can't leak through logs.
- **Backends:** a registry `{"tuya_lan": TuyaLanBackend}`. Each backend validates `connection` and `options` at load time and implements `move(device, direction)` and `status(device)`.
- **Movement:** `Home.up/down/stop(target)` act only on `shutter` devices. If a target resolves to devices but none of them are shutters, that's `UnknownTargetError`, listing the valid shutter targets.
- **Unchanged from phase 1:**
  - target resolution: `all`, then a device name or alias, then a room name or alias;
  - normalization (apostrophes, whitespace, casefold);
  - concurrent execution, with failures isolated per device;
  - result outcomes `ok` / `unreachable` / `not_confirmed` / `rejected`;
  - Tuya LAN values `on` / `off` / `stop` with state confirmation;
  - code 914 reported as unreachable;
  - the tinytuya logger capped at INFO;
  - failure warnings with the scan hint.

## CLI

`home-control --config PATH <command>`. `HOME_CONTROL_CONFIG` is used if `--config` is omitted; with neither set, the CLI prints usage and exits with code 2.

- `up | down | stop | status <target>`, `list`: as in phase 1.
- `import <tinytuya-devices.json>`: interactive. It asks for each device's name, room and aliases, then each new room's aliases, and writes a v1 file to `--config`. It refuses to overwrite an existing file without `--force`, and validates the result before saving.
- `scan`: finds the devices on the LAN by `connection.id` and rewrites changed `connection.ip` values in the file. Other fields are preserved as they were.
- Exit codes: `0` ok, `1` some device failed or wasn't found, `2` config or usage error. `status` exits `1` if any device returned an error.

## Packaging and release

- The repo `aGallea/home-control` is deleted and recreated **public**, with fresh history containing no device data.
- A GitHub Actions workflow on tag `v*` runs the tests, builds the wheel and sdist with `uv build`, and creates a GitHub Release with both files attached.
- Consumers pin the exact wheel URL:
  `home-control @ https://github.com/aGallea/home-control/releases/download/v0.2.0/home_control-0.2.0-py3-none-any.whl`
- The first release is `v0.2.0`; `0.1.0` was the unpublished phase-1 version.

## reachy-lychee changes

**Dependency:**
- Replace `"home-control"` and its `[tool.uv.sources]` path with the pinned wheel URL above.
- Live edits in development are opt-in: `uv pip install -e ../../../home-control`, documented in the README. They are not configured by default.

**Device file:**
- Lychee owns `home.json`, located by the same rule as `apple_tv.v1.json`:
  - `<instance_path>/home.json` when lychee has an instance path;
  - otherwise `$XDG_DATA_HOME/reachy_lychee/home.json` (default `~/.local/share/reachy_lychee/home.json`).
- `LYCHEE_HOME_CONFIG` overrides the path.

**`build_home(instance_path, path=None)`:**
- Calls `load_config_file` then `Home.from_config`.
- A missing file → `None` with an info log.
- `ConfigError` or any other exception → `None` with a warning. Lychee always starts.
- Each skipped device is logged as a warning.

**Unchanged:** the `home` tool's actions, schema and result shapes (`list` now returns `devices` instead of `shutters`).

**Robot install** (`scripts/install_on_robot.sh`):
- Drop the home-control rsync and `--no-deps` install.
- `scripts/deps_without.py` keeps direct URL requirements: it prints `name @ url` when the requirement has a URL. Without this, pip would look the bare name up on PyPI.
- The robot then installs home-control from the release URL like any other dependency.

**Migration (one-off, not committed):** convert the Mac's existing `~/.config/home-control/devices.toml` to `home.json` in lychee's data folder (mode 600), then delete the TOML file.

## Testing

**home-control:**
- the privacy guard test (above), run locally and in CI;
- schema validation: every rule above, including unknown type or backend → skipped;
- `from_config` building devices and backends;
- file helpers: permissions, unreadable files, invalid JSON, atomic save and mode;
- `Device` repr hides `connection`;
- all phase-1 behaviour tests, ported to the generic model with made-up devices;
- CLI with `--config` and the env var, `import`/`scan` on v1 files, `status` exit codes.

**lychee:**
- `build_home` path resolution (instance path, XDG, env override);
- missing, broken, or partly-unknown files;
- the tool's `list` shape;
- the robot helper printing `name @ url`;
- the full suite stays green.

**Release:**
- the workflow runs on a test tag;
- lychee `uv sync` installs from the release URL;
- the robot install is verified when the robot is reachable.

**Hardware:**
- `home-control --config <lychee home.json> status all` on the Mac;
- one up/stop pulse via lychee in the simulator.

## Out of scope

Lights and the `zigbee2mqtt` backend (the next phase, which uses this schema), positions, schedules.
