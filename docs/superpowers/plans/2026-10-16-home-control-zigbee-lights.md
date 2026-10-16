# home-control: Zigbee Lights — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `light` device type driven through Zigbee2MQTT over MQTT. Release it as home-control v0.3.0, and give reachy-lychee's `home` tool `on`/`off`.

**Architecture:**
- Backends declare the device types they support, and receive their settings from a new top-level `backends` section.
- `Zigbee2MqttBackend` opens one `aiomqtt` connection per command: subscribe to the device topic, publish to `/set` (or `/get` for status), then wait for the matching state key.
- `Home.on/off` mirror `move`, but act only on lights.
- Lychee pins the new release and routes `on`/`off` through the tool.

**Tech Stack:** Python ≥ 3.11, `aiomqtt==2.5.1` (paho-mqtt 2.x), tinytuya, pytest/pytest-asyncio, ruff, mypy strict, uv, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-16-home-control-zigbee-lights-design.md`. Read it, and its predecessor `2026-10-16-home-control-generic-config-design.md`, first.

## Global Constraints

**Locations and branches:**
- `$HC` is the home-control checkout (branch `feat/lights`). `$APPS` is the reachy-mini-apps checkout (branch `feat/lychee-home-shutters`), and `$LYCHEE` is `$APPS/reachy_lychee`.
- `$SCRATCH` is a private scratch directory outside every repo.

**Privacy (home-control is a public repo):**
- No real device names, room names, IPs, friendly names, MQTT credentials or the owner's email in any committed file, commit message, PR text or release note.
- Examples use the device "Kitchen spots", the friendly name `hall_switch`, and IPs from `192.0.2.0/24`.
- `tests/test_privacy.py` must stay green.
- `.git/hooks/pre-push` (local, not committed) must run clean on every push.

**MQTT facts** (verified against aiomqtt 2.5.1 and the owner's Mosquitto 2.x):
- `aiomqtt.Client(hostname, port, *, username, password, timeout, keepalive)` is an async context manager.
- A refused connection raises `aiomqtt.MqttError` ("[Errno 61] Connection refused"); a timeout also raises `MqttError`.
- A rejected login raises `aiomqtt.MqttCodeError`, whose `.rc.value` is `135`. Treat rc values `{4, 5, 134, 135}` as "refused the login".
- `client.subscribe(topic, qos=1)`, `client.publish(topic, payload, qos=1)`, and `async for message in client.messages`. `message.payload` is bytes.

**Zigbee2MQTT topics:**
- state is published on `<base>/<device>`;
- commands go to `<base>/<device>/set` with `{"state_<endpoint>": "ON"|"OFF"}`;
- status requests go to `<base>/<device>/get` with `{"state_<endpoint>": ""}`;
- with no endpoint, the key is `state`.

**Behaviour:**
- Default `timeout_s` 3.0, default port 1883, default base topic `zigbee2mqtt`.
- Outcomes:
  - the requested value reported → `OK`;
  - timeout → `NOT_CONFIRMED`;
  - connect failure → `UNREACHABLE`;
  - login refused → `REJECTED`;
  - another MQTT error after connecting → `REJECTED`.
- The MQTT password never appears in a repr, log line, error message or result.
- The "run: home-control scan" hint is only added for `tuya_lan` devices.

**Style:**
- home-control: ruff (E/F/W/I/C4, E501 ignored, line length 119), mypy strict.
- lychee: lint only the touched files; tests have no docstrings.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Two lights on the same physical switch, in one room command** ("off" on a room with two endpoints of the same device). Each command must confirm only on its own key. A state message that carries the other endpoint's change, with this endpoint still at the old value, must not confirm it. Pinned in Task 2: `test_other_endpoint_update_does_not_confirm`.
2. **A broker that accepts the connection but a device that never answers** (Zigbee2MQTT stopped, switch out of range). Expect `NOT_CONFIRMED` after `timeout_s`, not a hang. Pinned in Task 2: `test_timeout_is_not_confirmed`.
3. **The MQTT password leaking through `repr(backend)` or an error string.** Pinned in Task 1: `test_password_never_in_repr_or_errors`. Task 2: `test_errors_do_not_contain_password`.
4. **An older config with no `backends` section and only shutters.** It loads exactly as in v0.2.1; zigbee2mqtt is never configured and nothing errors. Pinned in Task 1: `test_shutter_only_config_needs_no_backends_section`.
5. **"Turn off the kitchen" where the room has shutters and lights.** `off` touches only the lights and `down` only the shutters. Pinned in Task 3: `test_mixed_room_on_touches_only_lights`.

---

## File Structure

**home-control** (`$HC`):

| File | Change |
|---|---|
| `pyproject.toml` | Version 0.3.0; add the `aiomqtt==2.5.1` dependency |
| `src/home_control/models.py` | Add `LIGHT = "light"` |
| `src/home_control/backends/base.py` | `Backend` gains `types`, `configure`, `switch` |
| `src/home_control/backends/tuya_lan.py` | `types`, a no-op `configure`, `switch` → `REJECTED` |
| `src/home_control/backends/zigbee2mqtt.py` | New `Zigbee2MqttBackend`, `Zigbee2MqttSettings` |
| `src/home_control/backends/__init__.py` | Registry includes `zigbee2mqtt` |
| `src/home_control/config.py` | `KNOWN_TYPES` adds `light`; `backends` section; configure and type check |
| `src/home_control/home.py` | `switch`/`on`/`off`; shared failure logging; per-backend hint |
| `src/home_control/cli.py` | `on` / `off` commands |
| `README.md` | Light example and `on` / `off` |
| Tests | `tests/test_config.py`, `tests/test_tuya_lan.py`, new `tests/test_zigbee2mqtt.py`, `tests/test_home.py`, `tests/test_cli.py` |

**reachy-mini-apps** (`$APPS`):

| File | Change |
|---|---|
| `reachy_lychee/pyproject.toml` | Pin the v0.3.0 wheel |
| `reachy_lychee/src/reachy_lychee/tools/home.py` | Actions `on` / `off`; new description |
| `reachy_lychee/tests/tools/test_home.py`, `reachy_lychee/tests/home/test_wiring.py` | Tests |

---

### Task 1: Backend types, settings, and config validation

**Files:**
- Modify: `src/home_control/models.py`, `src/home_control/backends/base.py`, `src/home_control/backends/tuya_lan.py`, `src/home_control/config.py`
- Test: `tests/test_config.py`, `tests/test_tuya_lan.py`

**Interfaces:**
- Produces:
  - `LIGHT = "light"` (models)
  - `Backend` protocol additions:
    - `types: frozenset[str]`
    - `configure(settings: Mapping[str, Any]) -> None` (raises `ConfigError`)
    - `async switch(device: Device, on: bool) -> CommandResult` (never raises)
  - `TuyaLanBackend.types == frozenset({"shutter"})`; `configure` accepts anything; `switch` returns `REJECTED` "not supported by tuya_lan"
  - `config.KNOWN_TYPES == frozenset({"shutter", "light"})`
  - `parse_config` order:
    1. parse devices;
    2. skip unknown types and backends;
    3. call `backend.configure(settings)` once for each backend used by at least one device, where `settings = data.get("backends", {}).get(name, {})`;
    4. if `device.type not in backend.types`, raise `ConfigError(f"device '{name}': type '{type}' is not supported by backend '{backend}'")`;
    5. then call `backend.validate(device)`.
  - `backends` must be an object if present, and each entry an object; otherwise `ConfigError` mentioning `backends`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_config.py`:

```python
class _FakeLightBackend:
    types = frozenset({"light"})

    def __init__(self):
        self.settings = None

    def configure(self, settings):
        if "host" not in settings:
            raise ConfigError("backend 'fakelight': backends.fakelight.host is required")
        self.settings = dict(settings)

    def validate(self, device):
        pass


def _light(name="Kitchen spots", room="Kitchen"):
    return {"name": name, "room": room, "type": "light", "backend": "fakelight", "connection": {"device": "hall_switch"}}


def test_light_type_is_known_and_backend_is_configured():
    fake = _FakeLightBackend()
    data = _with(lambda d: (d["devices"].append(_light()), d.update(backends={"fakelight": {"host": "192.0.2.20"}})))
    cfg = parse_config(data, {**default_backends(), "fakelight": fake})
    assert [d.name for d in cfg.devices][-1] == "Kitchen spots"
    assert fake.settings == {"host": "192.0.2.20"}


def test_backend_settings_missing_is_error():
    data = _with(lambda d: d["devices"].append(_light()))
    with pytest.raises(ConfigError, match="host is required"):
        parse_config(data, {**default_backends(), "fakelight": _FakeLightBackend()})


def test_type_not_supported_by_backend_is_error():
    data = _with(lambda d: d["devices"].append({**_light(), "backend": "tuya_lan"}))
    with pytest.raises(ConfigError, match=r"Kitchen spots.*'light'.*not supported.*'tuya_lan'"):
        _parse(data)


def test_unused_backend_is_not_configured():
    fake = _FakeLightBackend()
    data = _with(lambda d: d.update(backends={"fakelight": {}}))  # would fail configure, but no device uses it
    parse_config(data, {**default_backends(), "fakelight": fake})
    assert fake.settings is None


def test_unknown_backend_settings_ignored_and_bad_shapes_rejected():
    _parse(_with(lambda d: d.update(backends={"future_bus": {"anything": 1}})))
    with pytest.raises(ConfigError, match="backends"):
        _parse(_with(lambda d: d.update(backends=["x"])))
    with pytest.raises(ConfigError, match="backends"):
        _parse(_with(lambda d: d.update(backends={"tuya_lan": "x"})))


def test_shutter_only_config_needs_no_backends_section():
    cfg = _parse(BASE)
    assert len(cfg.devices) == 3 and cfg.skipped == ()
```

`light` is now a known type, so two existing tests need a type this version still doesn't know:
- in `test_unknown_type_and_backend_are_skipped` (`tests/test_config.py`), change the skipped device's type from `"light"` to `"sprinkler"` and expect `("Hall light", "unknown type 'sprinkler'")`;
- in `test_names_shape` (`tests/test_home.py`), change the extra device's `"type": "light"` to `"sprinkler"` and expect `[{"name": "Hall light", "reason": "unknown type 'sprinkler'"}]`.

Append to `tests/test_tuya_lan.py`:

```python
def test_tuya_declares_shutter_and_rejects_switch():
    import asyncio

    b = TuyaLanBackend()
    assert b.types == frozenset({"shutter"})
    b.configure({})
    r = asyncio.run(b.switch(_device(), True))
    assert r.outcome is Outcome.REJECTED and "not supported" in (r.detail or "")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd $HC && uv run pytest tests/test_config.py tests/test_tuya_lan.py -q`
Expected: the new tests FAIL. For example, `test_type_not_supported_by_backend_is_error` fails with "DID NOT RAISE" (the light is skipped as an unknown type), and `test_tuya_declares_shutter_and_rejects_switch` fails with an `AttributeError` on `types`.

- [ ] **Step 3: Implement.**

In `models.py`, after `SHUTTER = "shutter"`, add:

```python
LIGHT = "light"
```

In `backends/base.py`:
- add `from collections.abc import Mapping`;
- add the following to the `Backend` protocol, before `validate`:

```python
    types: frozenset[str]

    def configure(self, settings: Mapping[str, Any]) -> None:
        """Apply this backend's `backends` entry from the config; raise ConfigError if invalid."""
        ...
```

and after `move`:

```python
    async def switch(self, device: Device, on: bool) -> CommandResult:
        """Turn a light on or off; never raises."""
        ...
```

In `backends/tuya_lan.py`:
- add `from collections.abc import Callable, Mapping` (replacing the `Callable` import);
- in `TuyaLanBackend`, add the class attribute `types = frozenset({SHUTTER})`, importing `SHUTTER` from `home_control.models`;
- add these methods:

```python
    def configure(self, settings: Mapping[str, Any]) -> None:
        """tuya_lan needs no backend-level settings."""

    async def switch(self, device: Device, on: bool) -> CommandResult:
        """Lights are not driven over tuya_lan."""
        return CommandResult(device.name, Outcome.REJECTED, "on/off is not supported by tuya_lan")
```

In `config.py`:
- import `LIGHT` from `home_control.models`;
- set `KNOWN_TYPES = frozenset({SHUTTER, LIGHT})`;
- add this helper:

```python
def _parse_backend_settings(raw: Any) -> dict[str, dict[str, Any]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict) or not all(isinstance(v, dict) for v in raw.values()):
        raise ConfigError("backends must be an object mapping backend name to its settings object")
    return {str(k): v for k, v in raw.items()}
```

In `parse_config`, replace the device loop with a two-pass version:

```python
    settings = _parse_backend_settings(data.get("backends"))
    parsed: list[Device] = []
    skipped: list[tuple[str, str]] = []
    for i, raw in enumerate(raw_devices):
        device = _parse_device(i, raw, rooms)
        if device.type not in KNOWN_TYPES:
            skipped.append((device.name, f"unknown type '{device.type}'"))
        elif device.backend not in backends:
            skipped.append((device.name, f"unknown backend '{device.backend}'"))
        else:
            parsed.append(device)
    for name in dict.fromkeys(d.backend for d in parsed):
        backends[name].configure(settings.get(name, {}))
    for device in parsed:
        backend = backends[device.backend]
        if device.type not in backend.types:
            raise ConfigError(
                f"device '{device.name}': type '{device.type}' is not supported by backend '{device.backend}'"
            )
        backend.validate(device)
    devices = parsed
```

The existing lines after the loop (`rooms.setdefault`, `replace(...)`, `_check_names`, the skipped warnings, the return) stay as they are and use `devices`.

- [ ] **Step 4: Run all checks**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass. The fake backends in `tests/test_home.py` and `tests/test_cli.py` still work because they're plain classes. If mypy complains that those fakes lack `types` or `configure`, that's fine: tests aren't type-checked (mypy covers `src/` only). Then add `types = frozenset({"shutter"})` and `def configure(self, settings): pass` to the `FakeBackend` classes in `tests/test_home.py` and `tests/test_cli.py`. Without them, `parse_config` raises `AttributeError`. Rerun until green.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: backends declare supported types and take settings from the config

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Zigbee2MQTT backend

**Files:**
- Create: `src/home_control/backends/zigbee2mqtt.py`
- Modify: `src/home_control/backends/__init__.py`, `src/home_control/__init__.py`, `pyproject.toml` (add the `aiomqtt==2.5.1` dependency; version `0.3.0`)
- Test: `tests/test_zigbee2mqtt.py`

**Interfaces:**
- Consumes: the `Backend` protocol (Task 1); `Device`, `CommandResult`, `Outcome`, `LIGHT`, `ConfigError`, `BackendError`
- Produces:
  - `Zigbee2MqttSettings` (frozen: `host`, `port=1883`, `username=None`, `password=None` (repr=False), `base_topic="zigbee2mqtt"`, `timeout_s=3.0`)
  - `Zigbee2MqttBackend(client_factory: Callable[[Zigbee2MqttSettings], Any] | None = None)` with:
    - `types = frozenset({"light"})`
    - `configure`, `validate`, `move` (returns `REJECTED`), `switch`, `status`
    - `_make_client(settings)`
  - `default_backends()` → `{"tuya_lan": ..., "zigbee2mqtt": Zigbee2MqttBackend()}`

- [ ] **Step 1: Write the failing tests** (`tests/test_zigbee2mqtt.py`)

```python
import asyncio
import json
from types import SimpleNamespace

import aiomqtt
import pytest

from home_control.backends import default_backends
from home_control.backends.base import BackendError
from home_control.backends.zigbee2mqtt import Zigbee2MqttBackend, Zigbee2MqttSettings
from home_control.errors import ConfigError
from home_control.models import LIGHT, Device, Outcome

SETTINGS = {"host": "192.0.2.20", "username": "homecontrol", "password": "s3cret-example"}


def _light(endpoint="center", device="hall_switch"):
    conn = {"device": device} if endpoint is None else {"device": device, "endpoint": endpoint}
    return Device("Kitchen spots", "Kitchen", LIGHT, "zigbee2mqtt", conn)


class FakeClient:
    """Scripted aiomqtt.Client stand-in: replies to publishes with queued state messages."""

    def __init__(self, replies=None, connect_error=None, publish_error=None):
        self.replies = list(replies or [])  # each: dict payload sent after a publish
        self.connect_error = connect_error
        self.publish_error = publish_error
        self.subscribed: list[str] = []
        self.published: list[tuple[str, dict]] = []
        self._queue: asyncio.Queue = asyncio.Queue()

    async def __aenter__(self):
        if self.connect_error:
            raise self.connect_error
        return self

    async def __aexit__(self, *exc):
        return False

    async def subscribe(self, topic, qos=0):
        self.subscribed.append(topic)

    async def publish(self, topic, payload=None, qos=0):
        if self.publish_error:
            raise self.publish_error
        self.published.append((topic, json.loads(payload)))
        for reply in self.replies:
            self._queue.put_nowait(SimpleNamespace(payload=json.dumps(reply).encode()))
        self.replies = []

    @property
    def messages(self):
        async def gen():
            while True:
                yield await self._queue.get()

        return gen()


def _backend(client, settings=None):
    b = Zigbee2MqttBackend(client_factory=lambda s: client)
    b.configure({**SETTINGS, **(settings or {})})
    return b


def test_registry_includes_zigbee2mqtt():
    assert isinstance(default_backends()["zigbee2mqtt"], Zigbee2MqttBackend)


def test_configure_defaults_and_validation():
    b = Zigbee2MqttBackend()
    b.configure({"host": "192.0.2.20"})
    assert b.settings == Zigbee2MqttSettings(host="192.0.2.20")
    assert b.settings.port == 1883 and b.settings.base_topic == "zigbee2mqtt" and b.settings.timeout_s == 3.0
    for bad, match in [
        ({}, "host"),
        ({"host": "h", "port": 0}, "port"),
        ({"host": "h", "port": "1883"}, "port"),
        ({"host": "h", "username": "u"}, "username and password"),
        ({"host": "h", "timeout_s": 0}, "timeout_s"),
        ({"host": "h", "base_topic": ""}, "base_topic"),
    ]:
        with pytest.raises(ConfigError, match=match):
            Zigbee2MqttBackend().configure(bad)


def test_validate_connection_fields():
    b = _backend(FakeClient())
    b.validate(_light())
    b.validate(_light(endpoint=None))
    for conn, match in [
        ({}, "connection.device"),
        ({"device": "a/b"}, "connection.device"),
        ({"device": "x", "endpoint": "l-1"}, "connection.endpoint"),
    ]:
        with pytest.raises(ConfigError, match=match):
            b.validate(Device("Kitchen spots", "Kitchen", LIGHT, "zigbee2mqtt", conn))


def test_password_never_in_repr_or_errors():
    b = _backend(FakeClient())
    assert "s3cret-example" not in repr(b) and "s3cret-example" not in repr(b.settings)


async def test_switch_on_publishes_and_confirms():
    client = FakeClient(replies=[{"state_center": "ON", "state_right": "OFF", "linkquality": 120}])
    r = await _backend(client).switch(_light(), True)
    assert r.ok
    assert client.subscribed == ["zigbee2mqtt/hall_switch"]
    assert client.published == [("zigbee2mqtt/hall_switch/set", {"state_center": "ON"})]


async def test_switch_without_endpoint_uses_state_key_and_base_topic():
    client = FakeClient(replies=[{"state": "OFF"}])
    r = await _backend(client, {"base_topic": "z2m"}).switch(_light(endpoint=None), False)
    assert r.ok and client.published == [("z2m/hall_switch/set", {"state": "OFF"})]
    assert client.subscribed == ["z2m/hall_switch"]


async def test_other_endpoint_update_does_not_confirm():
    client = FakeClient(replies=[{"state_center": "OFF", "state_right": "ON"}, "not json", {"state_center": "ON"}])
    r = await _backend(client, {"timeout_s": 0.5}).switch(_light(), True)
    assert r.ok  # ignored the first two messages, confirmed on the third


async def test_timeout_is_not_confirmed():
    client = FakeClient(replies=[{"state_center": "OFF"}])
    r = await _backend(client, {"timeout_s": 0.1}).switch(_light(), True)
    assert r.outcome is Outcome.NOT_CONFIRMED and "did not report" in (r.detail or "")


async def test_connect_failure_is_unreachable():
    client = FakeClient(connect_error=aiomqtt.MqttError("[Errno 61] Connection refused"))
    r = await _backend(client).switch(_light(), True)
    assert r.outcome is Outcome.UNREACHABLE and "192.0.2.20:1883" in (r.detail or "")


async def test_auth_failure_is_rejected():
    client = FakeClient(connect_error=aiomqtt.MqttCodeError(135, "Not authorized"))
    r = await _backend(client).switch(_light(), True)
    assert r.outcome is Outcome.REJECTED and "refused the login" in (r.detail or "")


async def test_other_mqtt_error_after_connect_is_rejected():
    client = FakeClient(publish_error=aiomqtt.MqttError("boom"))
    r = await _backend(client).switch(_light(), True)
    assert r.outcome is Outcome.REJECTED and "boom" in (r.detail or "")


async def test_errors_do_not_contain_password():
    for err in (aiomqtt.MqttError("[Errno 61] Connection refused"), aiomqtt.MqttCodeError(135, "Not authorized")):
        r = await _backend(FakeClient(connect_error=err)).switch(_light(), True)
        assert "s3cret-example" not in (r.detail or "")


async def test_status_reads_state():
    client = FakeClient(replies=[{"state_center": "ON", "linkquality": 87}])
    assert await _backend(client).status(_light()) == {"state": "ON", "linkquality": 87}
    assert client.published == [("zigbee2mqtt/hall_switch/get", {"state_center": ""})]


async def test_status_timeout_and_unreachable_raise():
    with pytest.raises(BackendError) as exc:
        await _backend(FakeClient(), {"timeout_s": 0.1}).status(_light())
    assert exc.value.outcome is Outcome.NOT_CONFIRMED
    with pytest.raises(BackendError) as exc:
        await _backend(FakeClient(connect_error=aiomqtt.MqttError("refused"))).status(_light())
    assert exc.value.outcome is Outcome.UNREACHABLE


async def test_move_not_supported():
    from home_control.models import Direction

    r = await _backend(FakeClient()).move(_light(), Direction.UP)
    assert r.outcome is Outcome.REJECTED


def test_default_client_factory_passes_settings(monkeypatch):
    calls = {}

    class FakeAioClient:
        def __init__(self, *args, **kwargs):
            calls["args"], calls["kwargs"] = args, kwargs

    monkeypatch.setattr("home_control.backends.zigbee2mqtt.aiomqtt.Client", FakeAioClient)
    b = Zigbee2MqttBackend()
    b.configure({**SETTINGS, "port": 1884, "timeout_s": 2.5})
    b._make_client(b.settings)
    assert calls["args"] == ("192.0.2.20", 1884)
    assert calls["kwargs"] == {"username": "homecontrol", "password": "s3cret-example", "timeout": 2.5, "keepalive": 10}
```

Note: `FakeClient(replies=[..., "not json", ...])` sends `json.dumps("not json")`, a JSON string rather than an object, which the backend must ignore.

- [ ] **Step 2: Run to verify failure**

Run: `uv add "aiomqtt==2.5.1" && uv run pytest tests/test_zigbee2mqtt.py -q`
Expected: a collection error, `No module named 'home_control.backends.zigbee2mqtt'`.

- [ ] **Step 3: Implement** `src/home_control/backends/zigbee2mqtt.py`

```python
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
        return aiomqtt.Client(
            settings.host,
            settings.port,
            username=settings.username,
            password=settings.password,
            timeout=settings.timeout_s,
            keepalive=10,
        )

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
```

In `backends/__init__.py`, import `Zigbee2MqttBackend` and return `{"tuya_lan": TuyaLanBackend(), "zigbee2mqtt": Zigbee2MqttBackend()}`. Add `Zigbee2MqttBackend` to `__all__` there and in `src/home_control/__init__.py`, and add `LIGHT` to the package exports.

In `pyproject.toml`, set `version = "0.3.0"` and make sure `dependencies` is `["tinytuya>=1.17,<1.18", "aiomqtt==2.5.1"]`. `uv add` already added the second one.

- [ ] **Step 4: Run all checks**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass. If mypy rejects `asyncio.timeout` under `python_version = "3.11"`, that's a wrong expectation: it exists in 3.11. Check the import instead.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: zigbee2mqtt backend for lights (aiomqtt, per-command connection, confirmed state)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Home on/off and CLI

**Files:**
- Modify: `src/home_control/home.py`, `src/home_control/cli.py`, `README.md`
- Test: `tests/test_home.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `Backend.switch` (Task 1), `LIGHT`
- Produces:
  - `Home.switch(target: str, on: bool) -> list[CommandResult]`
  - `Home.on(target)` / `Home.off(target)`
  - CLI `on <target>` / `off <target>`, with the same output and exit codes as `up`/`down`
  - Failure warnings name the action (`up`/`down`/`stop`/`on`/`off`). The scan hint appears only when the failed device's backend is `tuya_lan`.

- [ ] **Step 1: Write the failing tests.** In `tests/test_home.py`:
  - give `FakeBackend` `types = frozenset({"shutter", "light"})` and `def configure(self, settings): pass` (if Task 1 didn't already);
  - add `async def switch(self, device, on)`, which records `(device.name, "on" if on else "off")` in `self.calls` and returns OK, or the outcome in `self.fail`.

Then append:

```python
LIGHTS_CONFIG = {
    "version": 1,
    "devices": [
        _dev("Kitchen left", "Kitchen", "a"),
        _dev("Kitchen spots", "Kitchen", "b", dtype="light"),
        _dev("Kitchen strip", "Kitchen", "c", dtype="light"),
        _dev("Porch lamp", "Porch", "d", dtype="light"),
    ],
}


async def test_mixed_room_on_touches_only_lights():
    backend = FakeBackend()
    home = _home(backend, LIGHTS_CONFIG)
    results = await home.off("Kitchen")
    assert sorted(r.device_name for r in results) == ["Kitchen spots", "Kitchen strip"]
    assert sorted(backend.calls) == [("Kitchen spots", "off"), ("Kitchen strip", "off")]
    backend.calls.clear()
    await home.down("Kitchen")
    assert backend.calls == [("Kitchen left", Direction.DOWN)]


async def test_on_all_and_light_less_target():
    backend = FakeBackend()
    home = _home(backend, LIGHTS_CONFIG)
    assert len(await home.on("all")) == 3
    with pytest.raises(UnknownTargetError) as exc:
        await home.on("Kitchen left")
    assert exc.value.valid == ["Kitchen spots", "Kitchen strip", "Porch lamp", "Kitchen", "Porch", "all"]


async def test_light_failures_logged_without_scan_hint(caplog):
    backend = FakeBackend(fail={"Porch lamp": Outcome.UNREACHABLE})
    with caplog.at_level("WARNING", logger="home_control.home"):
        await _home(backend, LIGHTS_CONFIG).on("Porch")
    assert "on Porch lamp: unreachable" in caplog.text and "home-control scan" not in caplog.text
```

In `tests/test_cli.py`:
- give `FakeBackend` `types = frozenset({"shutter", "light"})` and `configure`, plus a `switch` that records `(device.name, on)`;
- in `CONFIG`, change the "Hall light" device's `"type"` to `"sprinkler"`, keeping `"backend": "zigbee2mqtt"`. `list` then still has one skipped device, and `scan` (which only looks at `tuya_lan` devices) still leaves it alone;
- update `test_list_includes_skipped` to expect `unknown type 'sprinkler'`.

Then append:

```python
def test_on_off_commands(tmp_path, backend, capsys):
    path = tmp_path / "home.json"
    save_config_file(path, {"version": 1, "devices": [
        {"name": "Kitchen spots", "room": "Kitchen", "type": "light", "backend": "tuya_lan", "connection": {}},
    ]})
    assert cli.main(["--config", str(path), "on", "Kitchen"]) == 0
    assert "Kitchen spots: ok" in capsys.readouterr().out
    assert cli.main(["--config", str(path), "off", "Kitchen", "spots"]) == 0
```

The CLI tests swap every backend for the fake through `_backends`, so the test light can name `tuya_lan` as its backend. The fake's `types` include `light`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_home.py tests/test_cli.py -q`
Expected: `AttributeError: 'Home' object has no attribute 'off'`, and argparse `invalid choice: 'on'`.

- [ ] **Step 3: Implement.** In `home.py`, import `LIGHT`, then replace the logging loop in `move` with a call to a shared helper, and add `switch` / `on` / `off`:

```python
    def _log_failures(self, action: str, results: list[CommandResult]) -> None:
        backend_of = {d.name: d.backend for d in self._devices}
        for r in results:
            if not r.ok:
                hint = ""
                if r.outcome is Outcome.UNREACHABLE and backend_of.get(r.device_name) == "tuya_lan":
                    hint = "; if its IP changed, run: home-control scan"
                logger.warning("%s %s: %s (%s)%s", action, r.device_name, r.outcome.value, r.detail, hint)

    async def _safe_switch(self, device: Device, on: bool) -> CommandResult:
        try:
            return await self._backends[device.backend].switch(device, on)
        except Exception as exc:  # a backend bug must not break the other devices
            return CommandResult(device.name, Outcome.REJECTED, f"{type(exc).__name__}: {exc}")

    async def switch(self, target: str, on: bool) -> list[CommandResult]:
        """Turn every light the target names on or off, concurrently."""
        lights = [d for d in self._devices if d.type == LIGHT]
        found = self._match(target, lights)
        if not found:
            raise UnknownTargetError(target, self.valid_names(LIGHT))
        results = list(await asyncio.gather(*(self._safe_switch(d, on) for d in found)))
        self._log_failures("on" if on else "off", results)
        return results

    async def on(self, target: str) -> list[CommandResult]:
        """Turn the target's lights on."""
        return await self.switch(target, True)

    async def off(self, target: str) -> list[CommandResult]:
        """Turn the target's lights off."""
        return await self.switch(target, False)
```

In `move`, after `results = ...`, replace the `for r in results:` block with `self._log_failures(direction.value, results)`.

In `cli.py`:
- change the subparser loop to `for name in ("up", "down", "stop", "on", "off", "status"):`;
- replace `results = asyncio.run(home.move(target, Direction(args.command)))` with:

```python
        if args.command in ("on", "off"):
            results = asyncio.run(home.switch(target, args.command == "on"))
        else:
            results = asyncio.run(home.move(target, Direction(args.command)))
```

In `README.md`:
- change the intro sentence to "Today it drives Tuya Wi-Fi curtain/shutter switches over the LAN (`tuya_lan`) and lights through Zigbee2MQTT (`zigbee2mqtt`).";
- change the install URL to v0.3.0;
- add a `"backends"` block and a light device to the JSON example, exactly as in the spec's example (hall_switch, `192.0.2.20`, password `example`);
- add `home-control --config path/to/home.json off Kitchen` to the CLI list;
- add the sentence: "The MQTT password lives only in your device file; it never appears in logs, errors or results."

- [ ] **Step 4: Run all checks**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all pass, privacy tests included.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Home.on/off and CLI on/off for lights

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Release v0.3.0

- [ ] **Step 1: Pre-push checks.** Run `uv run pytest -q tests/test_privacy.py`. Then `git push -u origin feat/lights`; the local pre-push hook runs the deny-list scan and must print `clean`.
- [ ] **Step 2: Open the PR and wait for CI.**

```bash
gh pr create --base main --head feat/lights --title "Zigbee lights via Zigbee2MQTT (v0.3.0)" --body-file "$SCRATCH/pr-lights.md"
gh pr checks --watch
```

Write the PR body with generic wording only:
- a summary of the light type, the zigbee2mqtt backend and on/off;
- a test plan;
- the line `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

- [ ] **Step 3: Merge and tag.**

```bash
gh pr merge --merge --delete-branch
git checkout main && git pull --ff-only
uv run pytest -q tests/test_privacy.py
git tag v0.3.0 && git push origin v0.3.0
```

Watch the release run (`gh run watch …`). Then check that `gh release view v0.3.0` lists `home_control-0.3.0-py3-none-any.whl` and the sdist, and that the wheel installs into a fresh venv in `$SCRATCH` from its URL.

---

### Task 5: lychee — pin v0.3.0, tool on/off

**Files:**
- Modify: `$LYCHEE/pyproject.toml`, `$LYCHEE/src/reachy_lychee/tools/home.py`
- Test: `$LYCHEE/tests/tools/test_home.py`, `$LYCHEE/tests/home/test_wiring.py`

**Interfaces:**
- Consumes: `Home.on/off` (v0.3.0)
- Produces: tool `home` with `ACTIONS = ("up", "down", "stop", "on", "off", "status", "list")`

- [ ] **Step 1: Write the failing tests.** In `tests/tools/test_home.py`, extend `_fake_home` so it also creates `home.on` and `home.off` as `AsyncMock`s, the same way as up/down/stop. Change `test_spec_shape`:

```python
    assert props["action"]["enum"] == ["up", "down", "stop", "on", "off", "status", "list"]
    for phrase in ("תפתח", "תסגור", "עצור", "תדליק", "תכבה", "never default to 'all'", "ask"):
        assert phrase in spec["description"]
```

Append:

```python
async def test_on_off_route_to_lights():
    home = _fake_home([CommandResult("Kitchen spots", Outcome.OK)])
    result = await Home()(_deps(home), action="off", target="Kitchen")
    home.off.assert_awaited_once_with("Kitchen")
    assert result == {"action": "off", "target": "Kitchen", "ok": ["Kitchen spots"], "failed": {}}
    await Home()(_deps(home), action="on", target="Kitchen spots")
    home.on.assert_awaited_once_with("Kitchen spots")
    home.down.assert_not_awaited()
```

In `tests/home/test_wiring.py`:
- change the expected URL prefix in `test_robot_install_uses_release_not_rsync` to `.../releases/download/v0.3.0/`;
- add a test:

```python
def test_build_home_loads_lights(tmp_path):
    from reachy_lychee.main import build_home

    path = tmp_path / "home.json"
    save_config_file(path, {**CONFIG,
        "backends": {"zigbee2mqtt": {"host": "192.0.2.20", "username": "u", "password": "p"}},
        "devices": [*CONFIG["devices"], {"name": "Kitchen spots", "room": "Kitchen", "type": "light",
                                         "backend": "zigbee2mqtt", "connection": {"device": "hall_switch", "endpoint": "center"}}]})
    home = build_home(None, path)
    assert [(d.name, d.type) for d in home.devices] == [("Kitchen left", "shutter"), ("Kitchen spots", "light")]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd $LYCHEE && uv run pytest tests/tools/test_home.py tests/home -q`
Expected: the enum assertion fails, `on` fails with "unknown action", the URL assertion fails, and `test_build_home_loads_lights` fails because v0.2.1 skips lights and the device list is shorter.

- [ ] **Step 3: Implement.**
  1. In `pyproject.toml`, replace `v0.2.1/home_control-0.2.1` with `v0.3.0/home_control-0.3.0`, then run `uv sync` and check that `uv pip show home-control` reports `0.3.0`.
  2. In `tools/home.py`, set `ACTIONS = ("up", "down", "stop", "on", "off", "status", "list")` and replace `description` with:

```python
    description = (
        "Control the user's home: window shutters (up / down / stop) and lights (on / off); read status or list "
        "names. Choose the action by WHAT the user names. Shutters: 'open / raise / תפתח את התריס / תרים' -> up; "
        "'close / lower / תסגור את התריס / תוריד' -> down; 'stop / עצור' -> stop. Lights: 'turn on / תדליק / תפתח "
        "את האור' -> on; 'turn off / תכבה / תסגור את האור' -> off. `target` is a device name, a room (acts on that "
        "room's shutters for up/down/stop, or its lights for on/off), or 'all'. If the user names only a room and it "
        "isn't clear whether they mean the lights or the shutters, ask; never default to 'all'. Call list to learn "
        "the names and which are lights or shutters. If a result has `failed` entries, tell the user which devices "
        "didn't respond instead of saying it's done. Confirm briefly after it works."
    )
```

  3. The `__call__` routing needs no change, because it already calls `getattr(home, action)(target)` for non-status actions. `on`/`off` are now in `ACTIONS` and exist on `Home`.

- [ ] **Step 4: Run tests and lint**

Run: `uv run pytest -q && uv run ruff check src/reachy_lychee/tools/home.py && uv run mypy 2>&1 | grep -c "tools/home.py"`
Expected: the full suite is green (more tests than the earlier 814), ruff is clean, and mypy reports `0`.

- [ ] **Step 5: Commit and push**

```bash
cd $APPS && git add reachy_lychee/pyproject.toml reachy_lychee/src/reachy_lychee/tools/home.py reachy_lychee/tests/tools/test_home.py reachy_lychee/tests/home/test_wiring.py
git commit -m "feat(lychee): home tool turns lights on/off (home-control v0.3.0)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

---

### Task 6: Owner's device file and hardware check (with the owner)

No committed code. Real values go only into the owner's `home.json`.

- [ ] **Step 1: Add the lights to `home.json`.**
  1. With a one-off script in `$SCRATCH`, load lychee's `home.json` with `load_config_file`.
  2. Add `backends.zigbee2mqtt` with the desktop's host, `username` and `password`. Set `password` to an empty placeholder string.
  3. Add the owner's light devices and room aliases, as agreed in conversation.
  4. Save it with `save_config_file`.
  5. The owner then fills in the real password with a command they run in their own terminal, so it never passes through the conversation:

     ```
     python3 -c "import json,getpass,os;p=os.path.expanduser('~/.local/share/reachy_lychee/home.json');d=json.load(open(p));d['backends']['zigbee2mqtt']['password']=getpass.getpass('MQTT password: ');open(p,'w').write(json.dumps(d,ensure_ascii=False,indent=2)+'\n')"
     ```
  6. Check with `stat -f %Lp` that the file mode is still `600`; if not, `chmod 600`.
- [ ] **Step 2: CLI check.**
  1. Run `home-control --config <home.json> list`. Expected: the lights appear with type `light`, and nothing is skipped.
  2. Run `status` for each light.
  3. Run `off`, then `on`, for each light, with the owner watching.
- [ ] **Step 3: Voice check.**
  1. Restart lychee in the simulator. Expected log: `Home control: N device(s)`.
  2. The owner says, in Hebrew and in English:
     - one light by its English name;
     - one light by its Hebrew alias;
     - one shutter command;
     - one ambiguous room-only request. Expected: the robot asks whether you mean the lights or the shutters.
- [ ] **Step 4: Update lychee PR #15.** Add lights to its summary and tick the checks that were done. Then make sure the repo's own deny-list scan stays clean before any further home-control push.
