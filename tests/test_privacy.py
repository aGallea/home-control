"""Guard: this repo is public and must contain no private data."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_EMAILS = {"5315995+agallea@users.noreply.github.com", "noreply@anthropic.com", "noreply@github.com"}
PRIVATE_IP = re.compile(r"\b(?:10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def _tracked_text_files() -> list[Path]:
    files = []
    for name in _git("ls-files", "--cached", "--others", "--exclude-standard").splitlines():
        path = ROOT / name
        if path.is_file():
            try:
                path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            files.append(path)
    return files


def test_no_private_ip_addresses():
    hits = [f"{p.relative_to(ROOT)}: {m}" for p in _tracked_text_files() for m in PRIVATE_IP.findall(p.read_text())]
    assert hits == []


def test_no_foreign_email_addresses():
    hits = [
        f"{p.relative_to(ROOT)}: {m}"
        for p in _tracked_text_files()
        for m in EMAIL.findall(p.read_text())
        if m.casefold() not in ALLOWED_EMAILS and not m.endswith(("@github.com", "@example.com"))
    ]
    assert hits == []


def test_commit_identities_are_noreply():
    proc = subprocess.run(["git", "log", "--all", "--format=%ae%n%ce"], cwd=ROOT, capture_output=True, text=True)
    emails = set(proc.stdout.split()) if proc.returncode == 0 else set()  # no commits yet -> nothing to check
    assert {e.casefold() for e in emails} <= ALLOWED_EMAILS


def test_commit_messages_have_no_private_ips_or_emails():
    proc = subprocess.run(["git", "log", "--all", "--format=%B"], cwd=ROOT, capture_output=True, text=True)
    text = proc.stdout if proc.returncode == 0 else ""
    assert PRIVATE_IP.findall(text) == []
    assert [m for m in EMAIL.findall(text) if m.casefold() not in ALLOWED_EMAILS] == []
