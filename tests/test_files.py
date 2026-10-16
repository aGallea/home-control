import os
import stat

import pytest

from home_control.errors import ConfigError
from home_control.files import load_config_file, save_config_file


def _write(tmp_path, text, mode=0o600):
    p = tmp_path / "home.json"
    p.write_text(text, encoding="utf-8")
    p.chmod(mode)
    return p


def test_load_valid_json(tmp_path):
    assert load_config_file(_write(tmp_path, '{"version": 1, "devices": []}')) == {"version": 1, "devices": []}


def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config_file(tmp_path / "nope.json")


def test_too_open_permissions_rejected(tmp_path):
    with pytest.raises(ConfigError, match="permissions"):
        load_config_file(_write(tmp_path, "{}", mode=0o644))


def test_invalid_json_rejected(tmp_path):
    with pytest.raises(ConfigError, match="JSON"):
        load_config_file(_write(tmp_path, "{nope"))


def test_non_object_rejected(tmp_path):
    with pytest.raises(ConfigError, match="object"):
        load_config_file(_write(tmp_path, "[1, 2]"))


def test_unreadable_rejected(tmp_path):
    d = tmp_path / "dir.json"
    d.mkdir(mode=0o700)
    with pytest.raises(ConfigError, match="cannot read"):
        load_config_file(d)


def test_non_utf8_rejected(tmp_path):
    p = tmp_path / "home.json"
    p.write_bytes(b"\xff\xfe{}")
    p.chmod(0o600)
    with pytest.raises(ConfigError, match="cannot read"):
        load_config_file(p)


def test_save_is_atomic_mode_600_and_roundtrips(tmp_path):
    path = tmp_path / "sub" / "home.json"
    data = {"version": 1, "rooms": {"Kitchen": {"aliases": ["המטבח"]}}, "devices": []}
    save_config_file(path, data)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert "המטבח" in path.read_text(encoding="utf-8")  # not \u-escaped
    assert load_config_file(path) == data
    assert [p.name for p in path.parent.iterdir()] == ["home.json"]
