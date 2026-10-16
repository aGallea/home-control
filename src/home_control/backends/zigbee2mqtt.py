"""Zigbee2MQTT backend: lights over an MQTT broker on the LAN (aiomqtt). One connection per command."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

import aiomqtt

from home_control.backends.base import BackendError
from home_control.errors import ConfigError
from home_control.models import LIGHT, CommandResult, Device, Direction, Outcome

_LOGIN_REFUSED = {4, 5, 134, 135}  # MQTT 3.1.1 and 5 "bad credentials" / "not authorized"
_ENDPOINT = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class Zigbee2MqttSettings:
    """Broker connection settings (from the config's backends.zigbee2mqtt)."""

    host: str
    port: int = 1883
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    base_topic: str = "zigbee2mqtt"
    timeout_s: float = 3.0


def _settings_from(raw: Mapping[str, Any]) -> Zigbee2MqttSettings:
    where = "backends.zigbee2mqtt"
    host = raw.get("host")
    if not isinstance(host, str) or not host.strip():
        raise ConfigError(f"{where}.host is required")
    port = raw.get("port", 1883)
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ConfigError(f"{where}.port must be an integer from 1 to 65535")
    username, password = raw.get("username"), raw.get("password")
    if (username is None) != (password is None):
        raise ConfigError(f"{where}: set both username and password, or neither")
    if username is not None and (not isinstance(username, str) or not isinstance(password, str)):
        raise ConfigError(f"{where}: username and password must be strings")
    base_topic = raw.get("base_topic", "zigbee2mqtt")
    if not isinstance(base_topic, str) or not base_topic.strip() or any(c in base_topic for c in "#+"):
        raise ConfigError(f"{where}.base_topic must be a non-empty topic without wildcards")
    timeout_s = raw.get("timeout_s", 3.0)
    if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or timeout_s <= 0:
        raise ConfigError(f"{where}.timeout_s must be a positive number")
    return Zigbee2MqttSettings(host.strip(), port, username, password, base_topic.strip().rstrip("/"), float(timeout_s))


def _state_key(device: Device) -> str:
    endpoint = device.connection.get("endpoint")
    return f"state_{endpoint}" if endpoint else "state"


def _payload(message: Any) -> dict[str, Any] | None:
    try:
        data = json.loads(message.payload)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class Zigbee2MqttBackend:
    """Lights exposed by Zigbee2MQTT, reached through its MQTT broker."""

    types = frozenset({LIGHT})

    def __init__(self, client_factory: Callable[[Zigbee2MqttSettings], Any] | None = None) -> None:
        self._factory = client_factory or self._make_client
        self.settings: Zigbee2MqttSettings | None = None

    def __repr__(self) -> str:
        if self.settings is None:
            return "Zigbee2MqttBackend(unconfigured)"
        return f"Zigbee2MqttBackend({self.settings.host}:{self.settings.port}, base_topic={self.settings.base_topic!r})"

    def configure(self, settings: Mapping[str, Any]) -> None:
        """Read backends.zigbee2mqtt; raise ConfigError if invalid."""
        self.settings = _settings_from(settings)

    def validate(self, device: Device) -> None:
        """Require connection.device (a topic segment) and an optional alphanumeric connection.endpoint."""
        name = device.connection.get("device")
        if not isinstance(name, str) or not name.strip() or any(c in name for c in "/#+"):
            raise ConfigError(f"device '{device.name}': connection.device must be a Zigbee2MQTT friendly name without / # +")
        endpoint = device.connection.get("endpoint")
        if endpoint is not None and (not isinstance(endpoint, str) or not _ENDPOINT.match(endpoint)):
            raise ConfigError(f"device '{device.name}': connection.endpoint must be letters, digits or _")

    def _make_client(self, settings: Zigbee2MqttSettings) -> Any:
        client = aiomqtt.Client(
            settings.host,
            settings.port,
            username=settings.username,
            password=settings.password,
            timeout=settings.timeout_s,
            keepalive=10,
        )
        # aiomqtt's timeout covers CONNACK onwards; bound the TCP connect too (paho defaults to 5 s).
        client._client.connect_timeout = settings.timeout_s
        return client

    def _require_settings(self) -> Zigbee2MqttSettings:
        if self.settings is None:
            raise ConfigError("backends.zigbee2mqtt is not configured")
        return self.settings

    async def _request(self, device: Device, suffix: str, body: dict[str, str], done: Callable[[dict[str, Any]], bool]
                       ) -> tuple[Outcome, str | dict[str, Any]]:
        """Publish body to <base>/<device>/<suffix> and wait for a state message satisfying `done`."""
        s = self._require_settings()
        topic = f"{s.base_topic}/{device.connection['device']}"
        async with AsyncExitStack() as stack:
            try:
                client = await stack.enter_async_context(self._factory(s))
            except aiomqtt.MqttCodeError as exc:
                if getattr(exc.rc, "value", exc.rc) in _LOGIN_REFUSED:
                    return Outcome.REJECTED, "MQTT broker refused the login (check username/password)"
                return Outcome.UNREACHABLE, f"MQTT broker {s.host}:{s.port} unreachable (code {getattr(exc.rc, 'value', exc.rc)})"
            except aiomqtt.MqttError as exc:
                return Outcome.UNREACHABLE, f"MQTT broker {s.host}:{s.port} unreachable ({exc})"
            try:
                await client.subscribe(topic, qos=1)
                await client.publish(f"{topic}/{suffix}", json.dumps(body), qos=1)
                async with asyncio.timeout(s.timeout_s):
                    async for message in client.messages:
                        if getattr(message, "retain", False):
                            continue  # a stored state from before this command, not a reply to it
                        data = _payload(message)
                        if data is not None and done(data):
                            return Outcome.OK, data
            except TimeoutError:
                return Outcome.NOT_CONFIRMED, "device did not report the new state (is Zigbee2MQTT running and the device in range?)"
            except aiomqtt.MqttError as exc:
                return Outcome.REJECTED, f"MQTT error: {exc}"
        return Outcome.NOT_CONFIRMED, "no state message received"

    async def switch(self, device: Device, on: bool) -> CommandResult:
        """Turn the light on/off and wait for Zigbee2MQTT to report it; never raises."""
        key, value = _state_key(device), "ON" if on else "OFF"
        try:
            outcome, detail = await self._request(device, "set", {key: value}, lambda d: d.get(key) == value)
        except Exception as exc:  # never let a backend bug escape into the caller
            return CommandResult(device.name, Outcome.REJECTED, f"{type(exc).__name__}: {exc}")
        return CommandResult(device.name, outcome, None if outcome is Outcome.OK else str(detail))

    async def status(self, device: Device) -> dict[str, Any]:
        """Return {"state": "ON"|"OFF"} (+ linkquality); raise BackendError on failure."""
        key = _state_key(device)
        outcome, detail = await self._request(device, "get", {key: ""}, lambda d: key in d)
        if outcome is not Outcome.OK or not isinstance(detail, dict):
            raise BackendError(outcome, str(detail))
        result: dict[str, Any] = {"state": detail[key]}
        if "linkquality" in detail:
            result["linkquality"] = detail["linkquality"]
        return result

    async def move(self, device: Device, direction: Direction) -> CommandResult:
        """Shutters are not driven over zigbee2mqtt in this version."""
        return CommandResult(device.name, Outcome.REJECTED, "up/down/stop is not supported by zigbee2mqtt")
