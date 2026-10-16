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
from home_control.models import Direction, normalize_name

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
    room_names: dict[str, str] = {}  # normalized -> first spelling entered
    devices: list[dict[str, Any]] = []
    for dev in exported:
        tuya_name = str(dev.get("name") or dev["id"])
        name = input(f"Name [{tuya_name}]: ").strip() or tuya_name
        room = input("Room: ").strip()
        room = room_names.setdefault(normalize_name(room), room)
        aliases = _split(input("Aliases (comma-separated, optional): "))
        if room not in rooms:
            rooms[room] = {"aliases": _split(input("Room aliases (comma-separated, optional): "))}
        device: dict[str, Any] = {"name": name}
        if aliases:
            device["aliases"] = aliases
        device.update(
            room=room,
            type="shutter",
            backend="tuya_lan",
            connection={
                "id": str(dev["id"]),
                "ip": str(dev["ip"]),
                "key": str(dev["key"]),
                "version": float(dev.get("version") or 3.3),
            },
        )
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
        print(
            f"file not found: {exc.filename}; create the device file with: "
            "home-control --config PATH import <devices.json>",
            file=sys.stderr,
        )
        return 2
    except (ConfigError, UnknownTargetError, json.JSONDecodeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for r in results:
        print(f"{r.device_name}: {r.outcome.value}" + (f" ({r.detail})" if r.detail else ""))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
