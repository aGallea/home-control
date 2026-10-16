# home-control: Zigbee lights via Zigbee2MQTT — Design

**Date:** 2026-10-16
**Status:** Draft, awaiting review
**Builds on:** `2026-10-16-home-control-generic-config-design.md` (config schema v1, privacy rules, release process)

## Goal

Add lights as a device type. They are controlled through a Zigbee2MQTT instance and its MQTT broker on the LAN, with the same guarantees as shutters:
- LAN only, no cloud;
- a command counts as successful only when the device reports the new state;
- failures are isolated per device;
- device data is supplied by the caller.

The release is **v0.3.0**. The config file stays **version 1**: the additions are optional, and older versions skip the new devices.

## Scope

**In scope:**
- device type `light` (on/off);
- backend `zigbee2mqtt`, with settings in a new top-level `backends` section;
- `Home.on` / `Home.off`;
- status for lights;
- CLI `on` / `off`;
- lychee's `home` tool actions `on` / `off`.

**Out of scope:**
- dimming, colour and scenes;
- Zigbee2MQTT availability tracking;
- reacting to physical button presses (no persistent subscription);
- TLS to the broker;
- pairing devices or managing Zigbee2MQTT itself.

## Config additions (schema version 1)

```json
{
  "version": 1,
  "backends": {
    "zigbee2mqtt": {"host": "192.0.2.20", "port": 1883, "username": "homecontrol", "password": "example", "base_topic": "zigbee2mqtt"}
  },
  "rooms": {"Kitchen": {"aliases": ["המטבח"]}},
  "devices": [
    {"name": "Kitchen spots", "aliases": ["ספוטים במטבח"], "room": "Kitchen", "type": "light", "backend": "zigbee2mqtt",
     "connection": {"device": "hall_switch", "endpoint": "center"}}
  ]
}
```

**`backends`:**
- An optional object mapping a backend name to its settings.
- A backend with no entry gets an empty settings object.
- Settings for backends this version doesn't know are ignored.

**`backends.zigbee2mqtt`:**

| Key | Required | Default | Meaning |
|---|---|---|---|
| `host` | yes | — | Broker host name or IP |
| `port` | no | `1883` | Broker TCP port (an integer from 1 to 65535) |
| `username`, `password` | no | none | Broker credentials. Both or neither. |
| `base_topic` | no | `zigbee2mqtt` | Zigbee2MQTT `base_topic` |
| `timeout_s` | no | `3.0` | Seconds to wait for the device to report the new state |

**Light `connection`:**
- `device` (str, required): the Zigbee2MQTT friendly name.
- `endpoint` (str, optional): for multi-gang devices, e.g. `left`, `center`, `right`.
- The state key is `state_<endpoint>`, or `state` when no endpoint is given.

**Validation**, in addition to the generic-config rules. Each failure raises `ConfigError` naming the device or backend and the field:
- Each backend declares the device types it supports: `tuya_lan` → `{shutter}`, `zigbee2mqtt` → `{light}`. A known type on a known backend that doesn't support it is an error.
- A device whose type or backend is unknown to this version is still skipped, not an error.
- A `zigbee2mqtt` device requires a valid `backends.zigbee2mqtt` section. A missing `host`, a bad `port`, or only one of `username`/`password` is an error.
- `connection.device` must be a non-empty string without `/`, `#` or `+` (MQTT topic characters). `connection.endpoint`, if present, must be a non-empty string of letters, digits and `_`.

**Secrets:** `password` is never included in a repr, a log line, an error message or a command result.

## Library changes

**Backends:**
- `Backend` gains:
  - `types: frozenset[str]`;
  - `configure(settings: Mapping[str, Any]) -> None` (raises `ConfigError`), called once with the backend's `backends` entry before any device is validated;
  - `async switch(device, on: bool) -> CommandResult` (never raises). Backends without lights return `REJECTED` with "not supported".
- `default_backends()` returns `{"tuya_lan": TuyaLanBackend(), "zigbee2mqtt": Zigbee2MqttBackend()}`.
- `parse_config`:
  1. calls `configure` on each backend that has at least one device;
  2. checks that each device's type is in its backend's `types`;
  3. then calls `validate`.

**`Zigbee2MqttBackend`:**
- **Library:** `aiomqtt`, with a client factory injected so tests can replace it. A new connection is opened per call, with keepalive 10 s and a connect timeout equal to `timeout_s`.
- **`switch(device, on)`:**
  1. Connect to the broker.
  2. Subscribe to `<base>/<device>`.
  3. Publish `{"<state_key>": "ON"|"OFF"}` to `<base>/<device>/set`, QoS 1.
  4. Wait up to `timeout_s` for a message on `<base>/<device>` whose JSON has `<state_key>` equal to the requested value. Messages without that key, or with the old value, are ignored.

  Outcomes:
  - the value is reported → `OK`;
  - timeout → `NOT_CONFIRMED`, "device did not report the new state (is Zigbee2MQTT running and the device in range?)";
  - connection refused, DNS failure or connect timeout → `UNREACHABLE`, "MQTT broker <host>:<port> unreachable";
  - not authorized or bad credentials → `REJECTED`, "MQTT broker refused the login";
  - any other MQTT error → `REJECTED` with its class name.
- **`status(device)`:** the same connection and subscription, then publish `{"<state_key>": ""}` to `<base>/<device>/get` and wait up to `timeout_s` for a message containing `<state_key>`. It returns `{"state": "ON"|"OFF"}`, plus `linkquality` if present. Failures raise `BackendError` with the same outcome mapping.
- **`move`** is not supported for lights; `Home` never routes shutter commands to this backend.

**`Home`:**
- `on(target)` / `off(target)` act on `light` devices only, concurrently, with failures isolated per device and logged as warnings, as `move` does.
- A target that names no lights raises `UnknownTargetError` listing `valid_names("light")`.
- `move` / `up` / `down` / `stop` stay shutters-only.
- `status` and `names` cover every type. `names()` device entries already include `type`.

**CLI:**
- New `on <target>` / `off <target>` commands, with the same output and exit codes as `up` / `down`.
- `scan` still only touches `tuya_lan` devices.

## reachy-lychee changes

**Dependency:** pin home-control `v0.3.0` (the wheel URL from the release).

**The `home` tool:**
- Actions become `up`, `down`, `stop` (shutters), `on`, `off` (lights), `status`, and `list`.
- The description tells the model:
  - **Lights:**
    - turn on / "תדליק" / "תפתח את האור" → `on`;
    - turn off / "תכבה" / "תסגור את האור" → `off`.
  - **Shutters:**
    - open / raise / "תפתח את התריס" / "תרים" → `up`;
    - close / lower / "תסגור את התריס" / "תוריד" → `down`;
    - "עצור" → `stop`.
  - Choose by what the user names. "Open/close the light" means on/off, and "open/close the shutter" means up/down.
  - If the user names only a room and it's unclear whether they mean lights or shutters, ask.
  - Never default to `all`.
  - Call `list` to learn the names and types.
- `on` / `off` call `home.on(target)` / `home.off(target)` and return the same `{action, target, ok, failed}` shape.
- An `UnknownTargetError` returns `{"error": ..., "valid": [...]}` as today.

**Device file:** the owner's `home.json` gains the `backends.zigbee2mqtt` section and the light devices. It stays mode 600 and is never committed.

## Error handling summary (lights)

| Situation | Outcome | Robot says |
|---|---|---|
| Broker down, or wrong host/port | `UNREACHABLE` | "I couldn't reach the light controller" |
| Wrong MQTT credentials | `REJECTED` | Reports the failure |
| Zigbee2MQTT down, or device out of range or unpaired | `NOT_CONFIRMED` | "I sent it, but the light didn't confirm" |
| Target names no lights | `UnknownTargetError` | Asks which one, using the valid light names |

## Testing

**home-control** (no network):
- Schema:
  - the `backends` section and its validation;
  - type/backend compatibility;
  - unknown backend settings ignored;
  - password hidden from reprs and errors.
- `Zigbee2MqttBackend`, with a fake client that records subscribes and publishes and feeds scripted messages:
  - exact topics and payloads with and without an endpoint;
  - confirmation;
  - stale or irrelevant messages ignored;
  - timeout → NOT_CONFIRMED;
  - connection error → UNREACHABLE;
  - auth error → REJECTED;
  - status reply parsing and timeout;
  - the default client factory passes host, port, credentials and timeouts to `aiomqtt.Client`.
- `Home`:
  - on/off touch only lights;
  - a mixed room;
  - all-lights;
  - a light-less target → error listing light names;
  - failures isolated and logged.
- CLI `on` / `off`.
- Privacy guard and release unchanged; the release workflow publishes v0.3.0.

**lychee:**
- the tool schema/enum and description phrases;
- `on`/`off` routing and result shapes;
- unknown target;
- `build_home` with a config containing lights.

**Hardware** (with the owner):
- CLI `on`/`off`/`status` for each configured light;
- voice in Hebrew and English through the simulator, covering lights, shutters, and an ambiguous room request.
