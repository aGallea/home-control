import logging
from unittest.mock import MagicMock

import pytest

from home_control.backends import default_backends
from home_control.backends.base import BackendError
from home_control.backends.tuya_lan import TuyaLanBackend, command_value, interpret_reply
from home_control.errors import ConfigError
from home_control.models import SHUTTER, Device, Direction, Outcome

CONN = {"id": "dev-kitchen-left", "ip": "192.0.2.10", "key": "0123456789abcdef"}


def _device(connection=None, options=None):
    return Device("Kitchen left", "Kitchen", SHUTTER, "tuya_lan", dict(CONN if connection is None else connection),
                  options=options or {})


def _backend(device_obj):
    made = []

    def factory(d):
        made.append(d)
        return device_obj

    return TuyaLanBackend(device_factory=factory), made


def test_registry_has_tuya_lan():
    assert isinstance(default_backends()["tuya_lan"], TuyaLanBackend)


def test_validate_accepts_minimal_and_full():
    b = TuyaLanBackend()
    b.validate(_device())
    b.validate(_device({**CONN, "version": 3.4}, {"inverted": True}))


@pytest.mark.parametrize("field", ["id", "ip", "key"])
def test_validate_requires_connection_fields(field):
    conn = {k: v for k, v in CONN.items() if k != field}
    with pytest.raises(ConfigError, match=rf"Kitchen left.*connection\.{field}"):
        TuyaLanBackend().validate(_device(conn))


def test_validate_rejects_bad_version_and_option():
    with pytest.raises(ConfigError, match=r"connection\.version"):
        TuyaLanBackend().validate(_device({**CONN, "version": "3.3"}))
    with pytest.raises(ConfigError, match=r"options\.inverted"):
        TuyaLanBackend().validate(_device(options={"inverted": "yes"}))


def test_command_values():
    assert [command_value(d, False) for d in Direction] == ["on", "off", "stop"]
    assert [command_value(d, True) for d in Direction] == ["off", "on", "stop"]


def test_interpret_confirmed():
    assert interpret_reply("Kitchen left", "on", {"dps": {"1": "on"}}).outcome is Outcome.OK


def test_interpret_none_and_other_value_not_confirmed():
    assert interpret_reply("Kitchen left", "on", None).outcome is Outcome.NOT_CONFIRMED
    r = interpret_reply("Kitchen left", "on", {"dps": {"1": "stop"}})
    assert r.outcome is Outcome.NOT_CONFIRMED and "stop" in (r.detail or "")


@pytest.mark.parametrize("code", ["901", "902", "905"])
def test_network_errors_unreachable(code):
    r = interpret_reply("Kitchen left", "on", {"Error": "Network Error", "Err": code, "Payload": None})
    assert r.outcome is Outcome.UNREACHABLE and code in (r.detail or "")


def test_no_reply_after_connect_is_unreachable():
    r = interpret_reply("Kitchen left", "on", {"Error": "Check device key or version", "Err": "914", "Payload": None})
    assert r.outcome is Outcome.UNREACHABLE
    assert "no reply" in (r.detail or "") and "914" in (r.detail or "")


def test_other_errors_rejected():
    r = interpret_reply("Kitchen left", "on", {"Error": "Invalid Payload", "Err": "904", "Payload": None})
    assert r.outcome is Outcome.REJECTED and "904" in (r.detail or "")


async def test_move_sends_on_off_stop_to_dps_1_and_respects_inverted():
    dev = MagicMock()
    dev.set_value.side_effect = lambda idx, val: {"dps": {idx: val}}
    backend, made = _backend(dev)
    for d in Direction:
        assert (await backend.move(_device(), d)).ok
    await backend.move(_device(options={"inverted": True}), Direction.UP)
    assert [c.args for c in dev.set_value.call_args_list] == [("1", "on"), ("1", "off"), ("1", "stop"), ("1", "off")]
    assert made[0].name == "Kitchen left"


async def test_move_exception_is_unreachable():
    dev = MagicMock()
    dev.set_value.side_effect = OSError("no route to host")
    backend, _ = _backend(dev)
    r = await backend.move(_device(), Direction.DOWN)
    assert r.outcome is Outcome.UNREACHABLE and "no route to host" in (r.detail or "")


async def test_status_returns_dps_or_raises():
    dev = MagicMock()
    dev.status.return_value = {"dps": {"1": "stop", "9": 40}}
    backend, _ = _backend(dev)
    assert await backend.status(_device()) == {"1": "stop", "9": 40}
    dev.status.return_value = {"Error": "Network Error: Device Unreachable", "Err": "905", "Payload": None}
    with pytest.raises(BackendError) as exc:
        await backend.status(_device())
    assert exc.value.outcome is Outcome.UNREACHABLE


def test_default_factory_builds_tinytuya_device(monkeypatch):
    calls = {}

    class FakeDevice:
        def __init__(self, *args, **kwargs):
            calls["args"], calls["kwargs"] = args, kwargs

    monkeypatch.setattr("home_control.backends.tuya_lan.tinytuya.Device", FakeDevice)
    TuyaLanBackend()._make_device(_device({**CONN, "version": 3.4}))
    assert calls["args"] == ("dev-kitchen-left", "192.0.2.10", "0123456789abcdef")
    assert calls["kwargs"] == {
        "version": 3.4, "connection_timeout": 3.0, "connection_retry_limit": 2, "connection_retry_delay": 0,
    }


def test_tinytuya_logger_capped_at_info():
    assert logging.getLogger("tinytuya").level == logging.INFO


def test_tuya_declares_shutter_and_rejects_switch():
    import asyncio

    b = TuyaLanBackend()
    assert b.types == frozenset({"shutter"})
    b.configure({})
    r = asyncio.run(b.switch(_device(), True))
    assert r.outcome is Outcome.REJECTED and "not supported" in (r.detail or "")
