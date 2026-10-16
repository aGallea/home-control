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
