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
