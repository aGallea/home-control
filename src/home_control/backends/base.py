"""Backend interface."""

from __future__ import annotations

from collections.abc import Mapping
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

    types: frozenset[str]

    def configure(self, settings: Mapping[str, Any]) -> None:
        """Apply this backend's `backends` entry from the config; raise ConfigError if invalid."""
        ...

    def validate(self, device: Device) -> None:
        """Check the device's connection/options; raise ConfigError naming the device and field."""
        ...

    async def move(self, device: Device, direction: Direction) -> CommandResult:
        """Move or stop a shutter; never raises."""
        ...

    async def switch(self, device: Device, on: bool) -> CommandResult:
        """Turn a light on or off; never raises."""
        ...

    async def status(self, device: Device) -> dict[str, Any]:
        """Return raw device state; raise BackendError on failure."""
        ...
