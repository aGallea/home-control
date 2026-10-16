from dataclasses import FrozenInstanceError

import pytest

from home_control.models import SHUTTER, CommandResult, Device, Direction, Outcome, normalize_name


def _device(**kw):
    base = {"name": "Kitchen left", "room": "Kitchen", "type": SHUTTER, "backend": "tuya_lan",
            "connection": {"id": "dev-kitchen-left", "ip": "192.0.2.10", "key": "0123456789abcdef"}}
    base.update(kw)
    return Device(**base)


def test_normalize_collapses_whitespace_casefolds_and_unifies_apostrophes():
    assert normalize_name("  Kid’s   ROOM ") == "kid's room"
    assert normalize_name("Kidʼs room") == "kid's room"
    assert normalize_name("ג׳ינס  חדר") == "ג'ינס חדר"


def test_direction_and_outcome_values():
    assert [d.value for d in Direction] == ["up", "down", "stop"]
    assert [o.value for o in Outcome] == ["ok", "unreachable", "not_confirmed", "rejected"]


def test_command_result_ok():
    assert CommandResult("Kitchen left", Outcome.OK).ok
    assert not CommandResult("Kitchen left", Outcome.UNREACHABLE, "timeout").ok


def test_device_defaults_and_frozen():
    d = _device()
    assert d.aliases == () and d.options == {}
    with pytest.raises(FrozenInstanceError):
        d.name = "x"  # type: ignore[misc]


def test_device_repr_hides_connection():
    text = repr(_device(options={"inverted": True}))
    assert "0123456789abcdef" not in text and "192.0.2.10" not in text and "inverted" not in text
    assert "Kitchen left" in text
