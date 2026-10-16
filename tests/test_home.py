import asyncio
from typing import Any

import pytest

from home_control.backends.base import BackendError
from home_control.config import parse_config
from home_control.errors import UnknownTargetError
from home_control.home import Home
from home_control.models import CommandResult, Device, Direction, Outcome


def _dev(name, room, dev_id, aliases=(), dtype="shutter"):
    return {"name": name, "room": room, "type": dtype, "backend": "fake", "aliases": list(aliases),
            "connection": {"id": dev_id}}


CONFIG = {
    "version": 1,
    "rooms": {"Kitchen": {"aliases": ["המטבח"]}, "Kid's room": {"aliases": ["חדר הילדים"]}},
    "devices": [
        _dev("Kitchen left", "Kitchen", "a", aliases=["מטבח שמאל"]),
        _dev("Kitchen right", "Kitchen", "b"),
        _dev("Kid's room", "Kid's room", "c"),
        _dev("Hall left", "Hall", "d"),
        _dev("Hall right", "Hall", "e"),
    ],
}


class FakeBackend:
    types = frozenset({"shutter"})

    def __init__(self, fail=None, raise_for=None):
        self.calls: list[tuple[str, Direction]] = []
        self.fail: dict[str, Outcome] = fail or {}
        self.raise_for: set[str] = raise_for or set()
        self.in_flight = 0
        self.max_in_flight = 0

    def validate(self, device: Device) -> None:
        pass

    def configure(self, settings):
        pass

    async def move(self, device: Device, direction: Direction) -> CommandResult:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        self.calls.append((device.name, direction))
        if device.name in self.raise_for:
            raise RuntimeError("boom")
        outcome = self.fail.get(device.name, Outcome.OK)
        return CommandResult(device.name, outcome, None if outcome is Outcome.OK else "x")

    async def status(self, device: Device) -> dict[str, Any]:
        if device.name in self.fail:
            raise BackendError(self.fail[device.name], "no answer")
        return {"1": "stop"}


def _home(backend=None, config=CONFIG):
    return Home.from_config(config, {"fake": backend or FakeBackend()})


def _names(devices):
    return [d.name for d in devices]


def test_from_config_with_default_backends_skips_fake_backend():
    home = Home.from_config(CONFIG)
    assert home.devices == () and len(home.skipped) == 5


def test_resolve_device_room_all():
    home = _home()
    assert _names(home.resolve("Kitchen left")) == ["Kitchen left"]
    assert _names(home.resolve("Kitchen")) == ["Kitchen left", "Kitchen right"]
    assert _names(home.resolve("hall")) == ["Hall left", "Hall right"]
    assert _names(home.resolve("Kid's room")) == ["Kid's room"]
    assert len(home.resolve("ALL")) == 5


def test_resolve_normalizes_and_accepts_hebrew():
    home = _home()
    assert _names(home.resolve("  KITCHEN ")) == ["Kitchen left", "Kitchen right"]
    assert _names(home.resolve("המטבח")) == ["Kitchen left", "Kitchen right"]
    assert _names(home.resolve("מטבח  שמאל")) == ["Kitchen left"]
    assert _names(home.resolve("Kid’s room")) == ["Kid's room"]
    assert _names(home.resolve("חדר הילדים")) == ["Kid's room"]


def test_unknown_and_empty_targets():
    home = _home()
    with pytest.raises(UnknownTargetError) as exc:
        home.resolve("garage")
    assert exc.value.target == "garage"
    assert {"Kitchen left", "Kitchen", "all"} <= set(exc.value.valid)
    with pytest.raises(UnknownTargetError):
        home.resolve("   ")


async def test_room_runs_concurrently():
    backend = FakeBackend()
    results = await _home(backend).down("Kitchen")
    assert [r.device_name for r in results] == ["Kitchen left", "Kitchen right"]
    assert all(r.ok for r in results) and backend.max_in_flight == 2


async def test_failures_isolated_and_logged(caplog):
    backend = FakeBackend(fail={"Hall left": Outcome.UNREACHABLE}, raise_for={"Kitchen left"})
    with caplog.at_level("WARNING", logger="home_control.home"):
        results = await _home(backend).up("all")
    by_name = {r.device_name: r for r in results}
    assert by_name["Hall left"].outcome is Outcome.UNREACHABLE
    assert by_name["Kitchen left"].outcome is Outcome.REJECTED and "boom" in (by_name["Kitchen left"].detail or "")
    assert sum(r.ok for r in results) == 3
    assert "Hall left" in caplog.text and "home-control scan" in caplog.text
    assert "Hall right" not in caplog.text


async def test_move_ignores_non_shutter_devices():
    config = {"version": 1, "devices": [
        _dev("Hall lamp", "Hall", "x", dtype="shutter"),
        _dev("Porch", "Porch", "y"),
    ]}
    home = _home(config=config)
    # make "Hall lamp" a non-shutter after parsing, as a future type would be
    home._devices = tuple(Device(d.name, d.room, "light" if d.name == "Hall lamp" else d.type, d.backend,
                                 d.connection) for d in home.devices)
    with pytest.raises(UnknownTargetError) as exc:
        await home.down("Hall")
    assert exc.value.valid == ["Porch", "all"]


async def test_status_maps_failures():
    status = await _home(FakeBackend(fail={"Kitchen right": Outcome.UNREACHABLE})).status("Kitchen")
    assert status == {"Kitchen left": {"1": "stop"}, "Kitchen right": {"error": "unreachable: no answer"}}


def test_names_shape():
    config = {**CONFIG, "devices": [*CONFIG["devices"], {**_dev("Hall light", "Hall", "z"), "type": "sprinkler"}]}
    names = _home(config=config).names()
    rooms = {r["name"]: r for r in names["rooms"]}
    assert rooms["Kitchen"] == {"name": "Kitchen", "aliases": ["המטבח"], "devices": ["Kitchen left", "Kitchen right"]}
    assert names["devices"][0] == {"name": "Kitchen left", "room": "Kitchen", "type": "shutter", "aliases": ["מטבח שמאל"]}
    assert names["skipped"] == [{"name": "Hall light", "reason": "unknown type 'sprinkler'"}]


def test_constructor_accepts_parsed_config():
    backends = {"fake": FakeBackend()}
    home = Home(parse_config(CONFIG, backends), backends)
    assert len(home.devices) == 5
