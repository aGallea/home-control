import copy

import pytest

from home_control.backends import default_backends
from home_control.config import parse_config
from home_control.errors import ConfigError

CONN = {"id": "dev-kitchen-left", "ip": "192.0.2.10", "key": "0123456789abcdef"}
BASE = {
    "version": 1,
    "rooms": {"Kitchen": {"aliases": ["המטבח"]}},
    "devices": [
        {"name": "Kitchen left", "aliases": ["מטבח שמאל"], "room": "Kitchen", "type": "shutter",
         "backend": "tuya_lan", "connection": dict(CONN)},
        {"name": "Kitchen right", "room": "kitchen", "type": "shutter", "backend": "tuya_lan",
         "connection": {**CONN, "id": "dev-kitchen-right", "ip": "192.0.2.11"}, "options": {"inverted": True}},
        {"name": "Hall", "room": "Hall", "type": "shutter", "backend": "tuya_lan",
         "connection": {**CONN, "id": "dev-hall", "ip": "192.0.2.12"}},
    ],
}


def _parse(data):
    return parse_config(data, default_backends())


def _with(mutate):
    data = copy.deepcopy(BASE)
    mutate(data)
    return data


def test_valid_config():
    cfg = _parse(BASE)
    assert [d.name for d in cfg.devices] == ["Kitchen left", "Kitchen right", "Hall"]
    assert cfg.devices[0].aliases == ("מטבח שמאל",)
    assert cfg.devices[1].room == "Kitchen"  # normalized to the rooms-section spelling
    assert cfg.devices[1].options == {"inverted": True}
    assert cfg.rooms == {"Kitchen": ("המטבח",), "Hall": ()}
    assert cfg.skipped == ()


def test_device_named_like_its_single_device_room_is_allowed():
    assert [d.name for d in _parse(BASE).devices][-1] == "Hall"


@pytest.mark.parametrize("version", [None, 2, "1", True])
def test_version_must_be_1(version):
    data = _with(lambda d: d.update(version=version) if version is not None else d.pop("version"))
    with pytest.raises(ConfigError, match="version"):
        _parse(data)


def test_devices_must_be_list_of_objects():
    with pytest.raises(ConfigError, match="devices"):
        _parse(_with(lambda d: d.update(devices={"x": 1})))
    with pytest.raises(ConfigError, match="devices"):
        _parse(_with(lambda d: d.update(devices=["x"])))


@pytest.mark.parametrize("field", ["name", "room", "type", "backend", "connection"])
def test_required_device_fields(field):
    data = _with(lambda d: d["devices"][0].pop(field))
    with pytest.raises(ConfigError, match=field):
        _parse(data)


def test_backend_validation_runs():
    data = _with(lambda d: d["devices"][0]["connection"].pop("key"))
    with pytest.raises(ConfigError, match=r"Kitchen left.*connection\.key"):
        _parse(data)


def test_unknown_type_and_backend_are_skipped():
    def add(d):
        d["devices"].append({"name": "Hall light", "room": "Hall", "type": "light", "backend": "zigbee2mqtt",
                             "connection": {"topic": "z2m/hall"}})
        d["devices"].append({"name": "Hall fan", "room": "Hall", "type": "shutter", "backend": "future_lan",
                             "connection": {}})

    cfg = _parse(_with(add))
    assert [d.name for d in cfg.devices] == ["Kitchen left", "Kitchen right", "Hall"]
    assert cfg.skipped == (("Hall light", "unknown type 'light'"), ("Hall fan", "unknown backend 'future_lan'"))


def test_duplicate_device_names_and_aliases_rejected():
    with pytest.raises(ConfigError, match=r"duplicate.*kitchen left"):
        _parse(_with(lambda d: d["devices"][1].update(name="  KITCHEN left ")))
    with pytest.raises(ConfigError, match=r"duplicate.*מטבח שמאל"):
        _parse(_with(lambda d: d["devices"][2].update(aliases=["מטבח שמאל"])))


def test_device_name_colliding_with_other_room_rejected():
    with pytest.raises(ConfigError, match=r"'kitchen'.*room"):
        _parse(_with(lambda d: d["devices"][2].update(aliases=["Kitchen"])))


def test_device_name_equal_to_own_multi_device_room_rejected():
    with pytest.raises(ConfigError, match=r"'kitchen'.*room"):
        _parse(_with(lambda d: d["devices"][0].update(name="Kitchen")))


def test_room_alias_collisions_rejected():
    def mutate(d):
        d["rooms"]["Hall"] = {"aliases": ["המטבח"]}

    with pytest.raises(ConfigError, match=r"duplicate.*המטבח"):
        _parse(_with(mutate))


@pytest.mark.parametrize("where", ["name", "alias", "room", "room_alias"])
def test_reserved_all_rejected(where):
    def mutate(d):
        dev = d["devices"][0]
        if where == "name":
            dev["name"] = "ALL"
        elif where == "alias":
            dev["aliases"] = ["all"]
        elif where == "room":
            dev["room"] = "All"
        else:
            d["rooms"]["Kitchen"]["aliases"] = ["all"]

    with pytest.raises(ConfigError, match="reserved"):
        _parse(_with(mutate))


def test_bad_aliases_and_rooms_types_rejected():
    with pytest.raises(ConfigError, match="aliases"):
        _parse(_with(lambda d: d["devices"][0].update(aliases="x")))
    with pytest.raises(ConfigError, match="rooms"):
        _parse(_with(lambda d: d.update(rooms=["Kitchen"])))
    with pytest.raises(ConfigError, match="options"):
        _parse(_with(lambda d: d["devices"][0].update(options=[1])))
