import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_no_private_data.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_no_private_data", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _repo(tmp_path, content: str, message: str = "add file") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    run = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    (repo / "f.txt").write_text(content, encoding="utf-8")
    run("add", "f.txt")
    run("commit", "-q", "-m", message)
    return repo


def _deny(tmp_path, data) -> Path:
    p = tmp_path / "deny.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_scans_its_own_repo_not_the_cwd(tmp_path, monkeypatch, capsys):
    mod = _load()
    monkeypatch.chdir(_repo(tmp_path, "nothing here"))
    deny = _deny(tmp_path, {"devices": [{"name": "Kitchen left"}]})  # "Kitchen" is in this repo's history
    assert mod.main([str(deny)]) == 1


def test_short_values_match_whole_words_only(tmp_path):
    mod = _load()
    repo = _repo(tmp_path, "the Den is here; garden is not a match")
    deny = _deny(tmp_path, {"rooms": {"Den": {}}})
    assert mod.main(["--repo", str(repo), str(deny)]) == 1
    repo2 = _repo(tmp_path / "b", "garden only")
    assert mod.main(["--repo", str(repo2), str(deny)]) == 0


def test_commit_messages_are_scanned(tmp_path):
    mod = _load()
    repo = _repo(tmp_path, "clean", message="tweak Secret Room")
    assert mod.main(["--repo", str(repo), str(_deny(tmp_path, {"rooms": {"Secret Room": {}}}))]) == 1


def test_missing_deny_file_is_usage_error(tmp_path, capsys):
    mod = _load()
    assert mod.main([str(tmp_path / "missing.json")]) == 2
    assert "cannot read" in capsys.readouterr().err
