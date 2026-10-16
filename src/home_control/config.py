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
    for display, aliases in rooms.values():
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
        room_key = normalize_name(room_owner[key])
        device = next(d for d in devices if d.name == device_name)
        own_single_room = (
            normalize_name(device.room) == room_key
            and len(members.get(room_key, [])) == 1
            and key == normalize_name(device.name) == room_key
        )
        if not own_single_room:
            raise ConfigError(
                f"name '{key}' of device '{device_name}' is also a room name or alias (room '{room_owner[key]}')"
            )


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
