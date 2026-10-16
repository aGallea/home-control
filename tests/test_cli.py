import json
from pathlib import Path
from typing import Any

import pytest

from home_control import cli
from home_control.backends.base import BackendError
from home_control.files import load_config_file, save_config_file
from home_control.models import CommandResult, Device, Direction, Outcome

CONFIG = {
    "version": 1,
    "rooms": {"Kitchen": {"aliases": ["המטבח"]}},
    "devices": [
        {"name": "Kitchen left", "room": "Kitchen", "type": "shutter", "backend": "tuya_lan",
         "connection": {"id": "dev-a", "ip": "192.0.2.10", "key": "0123456789abcdef"}},
        {"name": "Kitchen right", "room": "Kitchen", "type": "shutter", "backend": "tuya_lan",
         "connection": {"id": "dev-b", "ip": "192.0.2.11", "key": "0123456789abcdef", "version": 3.3},
         "options": {"inverted": True, "future_option": 7}},
        {"name": "Hall light", "room": "Hall", "type": "sprinkler", "backend": "zigbee2mqtt", "connection": {"topic": "t"}},
    ],
}


class FakeBackend:
    types = frozenset({"shutter", "light"})

    def __init__(self):
        self.fail: set[str] = set()
        self.status_fail: set[str] = set()
        self.calls: list[tuple[str, Direction]] = []

    def validate(self, device: Device) -> None:
        pass

    def configure(self, settings):
        pass

    async def move(self, device: Device, direction: Direction) -> CommandResult:
        self.calls.append((device.name, direction))
        if device.name in self.fail:
            return CommandResult(device.name, Outcome.UNREACHABLE, "timeout")
        return CommandResult(device.name, Outcome.OK)

    async def switch(self, device: Device, on: bool) -> CommandResult:
        self.calls.append((device.name, on))
        if device.name in self.fail:
            return CommandResult(device.name, Outcome.UNREACHABLE, "timeout")
        return CommandResult(device.name, Outcome.OK)

    async def status(self, device: Device) -> dict[str, Any]:
        if device.name in self.status_fail:
            raise BackendError(Outcome.UNREACHABLE, "timeout")
        return {"1": "stop"}


@pytest.fixture
def cfg(tmp_path: Path) -> Path:
    path = tmp_path / "home.json"
    save_config_file(path, CONFIG)
    return path


@pytest.fixture
def backend(monkeypatch) -> FakeBackend:
    fake = FakeBackend()
    monkeypatch.setattr(cli, "_backends", lambda: {"tuya_lan": fake})
    return fake


def test_up_room(cfg, backend, capsys):
    assert cli.main(["--config", str(cfg), "up", "Kitchen"]) == 0
    out = capsys.readouterr().out
    assert "Kitchen left: ok" in out and "Kitchen right: ok" in out


def test_env_var_and_multiword_target(cfg, backend, monkeypatch):
    monkeypatch.setenv("HOME_CONTROL_CONFIG", str(cfg))
    assert cli.main(["down", "Kitchen", "left"]) == 0
    assert backend.calls == [("Kitchen left", Direction.DOWN)]


def test_no_config_is_usage_error(monkeypatch, capsys):
    monkeypatch.delenv("HOME_CONTROL_CONFIG", raising=False)
    assert cli.main(["list"]) == 2
    assert "--config" in capsys.readouterr().err


def test_missing_file_is_usage_error(tmp_path, capsys):
    assert cli.main(["--config", str(tmp_path / "nope.json"), "list"]) == 2
    err = capsys.readouterr().err
    assert "file not found" in err and "import" in err


def test_failure_exit_1(cfg, backend, capsys):
    backend.fail = {"Kitchen right"}
    assert cli.main(["--config", str(cfg), "stop", "all"]) == 1
    assert "Kitchen right: unreachable (timeout)" in capsys.readouterr().out


def test_unknown_target_exit_2(cfg, backend, capsys):
    assert cli.main(["--config", str(cfg), "up", "garage"]) == 2
    assert "unknown target 'garage'" in capsys.readouterr().err


def test_list_includes_skipped(cfg, backend, capsys):
    assert cli.main(["--config", str(cfg), "list"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["rooms"][0]["devices"] == ["Kitchen left", "Kitchen right"]
    assert data["skipped"] == [{"name": "Hall light", "reason": "unknown type 'sprinkler'"}]


def test_status_exit_1_on_error(cfg, backend, capsys):
    assert cli.main(["--config", str(cfg), "status", "Kitchen left"]) == 0
    assert json.loads(capsys.readouterr().out) == {"Kitchen left": {"1": "stop"}}
    backend.status_fail = {"Kitchen right"}
    assert cli.main(["--config", str(cfg), "status", "Kitchen"]) == 1


EXPORT = [
    {"id": "dev-a", "name": "Tuya name A", "key": "0123456789abcdef", "ip": "192.0.2.10", "version": "3.3"},
    {"id": "dev-b", "name": "Tuya name B", "key": "0123456789abcdef", "ip": "192.0.2.11", "version": "3.3"},
]


def _answers(monkeypatch, answers):
    prompts = []
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or next(it))
    return prompts


def test_import_writes_v1(tmp_path, monkeypatch):
    export = tmp_path / "devices.json"
    export.write_text(json.dumps(EXPORT), encoding="utf-8")
    out = tmp_path / "home.json"
    prompts = _answers(monkeypatch, ["Kitchen left", "Kitchen", "מטבח שמאל", "המטבח", "", "Kitchen", ""])
    assert cli.main(["--config", str(out), "import", str(export)]) == 0
    data = load_config_file(out)
    assert data["version"] == 1
    assert data["rooms"] == {"Kitchen": {"aliases": ["המטבח"]}}
    assert [d["name"] for d in data["devices"]] == ["Kitchen left", "Tuya name B"]
    assert data["devices"][0] == {
        "name": "Kitchen left", "aliases": ["מטבח שמאל"], "room": "Kitchen", "type": "shutter", "backend": "tuya_lan",
        "connection": {"id": "dev-a", "ip": "192.0.2.10", "key": "0123456789abcdef", "version": 3.3},
    }
    assert sum("Room aliases" in p for p in prompts) == 1


def test_import_refuses_overwrite_and_invalid_result(cfg, tmp_path, monkeypatch, capsys):
    export = tmp_path / "devices.json"
    export.write_text(json.dumps(EXPORT), encoding="utf-8")
    assert cli.main(["--config", str(cfg), "import", str(export)]) == 2
    assert "--force" in capsys.readouterr().err
    out = tmp_path / "new.json"
    _answers(monkeypatch, ["Same", "Kitchen", "", "", "same", "Kitchen", ""])
    assert cli.main(["--config", str(out), "import", str(export)]) == 2
    assert "duplicate" in capsys.readouterr().err and not out.exists()


def test_import_bad_json_is_usage_error(tmp_path, capsys):
    export = tmp_path / "devices.json"
    export.write_text("{nope", encoding="utf-8")
    assert cli.main(["--config", str(tmp_path / "o.json"), "import", str(export)]) == 2


def test_scan_preserves_unknown_fields(cfg, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_scan", lambda: {"dev-a": {"ip": "192.0.2.50"}, "dev-b": {"ip": "192.0.2.11"}})
    assert cli.main(["--config", str(cfg), "scan"]) == 0
    assert "Kitchen left: 192.0.2.10 -> 192.0.2.50" in capsys.readouterr().out
    expected = json.loads(json.dumps(CONFIG))
    expected["devices"][0]["connection"]["ip"] = "192.0.2.50"
    assert load_config_file(cfg) == expected


def test_scan_missing_device_exit_1(cfg, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_scan", lambda: {"dev-a": {"ip": "192.0.2.10"}})
    assert cli.main(["--config", str(cfg), "scan"]) == 1
    assert "Kitchen right: not found on the LAN" in capsys.readouterr().out


def test_import_treats_room_spellings_as_one_room(tmp_path, monkeypatch):
    export = tmp_path / "devices.json"
    export.write_text(json.dumps(EXPORT), encoding="utf-8")
    out = tmp_path / "home.json"
    prompts = _answers(monkeypatch, ["A", "Kitchen", "", "המטבח", "B", " kitchen ", ""])
    assert cli.main(["--config", str(out), "import", str(export)]) == 0
    data = load_config_file(out)
    assert [d["room"] for d in data["devices"]] == ["Kitchen", "Kitchen"]
    assert data["rooms"] == {"Kitchen": {"aliases": ["המטבח"]}}
    assert sum("Room aliases" in p for p in prompts) == 1


def test_on_off_commands(tmp_path, backend, capsys):
    path = tmp_path / "home.json"
    save_config_file(path, {"version": 1, "devices": [
        {"name": "Kitchen spots", "room": "Kitchen", "type": "light", "backend": "tuya_lan", "connection": {}},
    ]})
    assert cli.main(["--config", str(path), "on", "Kitchen"]) == 0
    assert "Kitchen spots: ok" in capsys.readouterr().out
    assert cli.main(["--config", str(path), "off", "Kitchen", "spots"]) == 0
