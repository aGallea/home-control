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
