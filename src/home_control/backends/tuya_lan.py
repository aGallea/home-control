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
