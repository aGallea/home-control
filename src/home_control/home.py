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
