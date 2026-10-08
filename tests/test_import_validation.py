"""Tests for the pure validate_task() in import_tasks.py (no Django needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from import_tasks import validate_task


def test_valid_snapshot_task():
    task = {"title": "Article A", "snapshot_url": "http://x/s.png", "url": "http://x"}
    assert validate_task(task) == []


def test_valid_text_task():
    task = {"title": "Article B", "text": "Body text", "url": "http://y"}
    assert validate_task(task) == []


def test_missing_title():
    task = {"snapshot_url": "http://x/s.png", "url": "http://x"}
    assert any("title" in e for e in validate_task(task))


def test_missing_snapshot_and_text():
    task = {"title": "Article C", "url": "http://x"}
    assert any("snapshot_url" in e and "text" in e for e in validate_task(task))


def test_both_snapshot_and_text():
    task = {
        "title": "Article D",
        "snapshot_url": "http://x/s.png",
        "text": "Body",
        "url": "http://x",
    }
    assert validate_task(task) != []


def test_title_not_string():
    task = {"title": 42, "text": "Body", "url": "http://x"}
    assert any("title" in e for e in validate_task(task))


def test_url_not_string():
    task = {"title": "Article E", "text": "Body", "url": 42}
    assert any("'url' must be a string" in e for e in validate_task(task))

def test_task_mode_snapshot():
    from import_tasks import task_mode
    task = {"title": "A", "snapshot_url": "http://x/s.png", "url": "http://x"}
    assert task_mode(task) == "snapshot"


def test_task_mode_text():
    from import_tasks import task_mode
    task = {"title": "A", "text": "Body", "url": "http://x"}
    assert task_mode(task) == "text"


def test_task_mode_invalid_is_empty():
    from import_tasks import task_mode
    assert task_mode({"title": "A", "url": "http://x"}) == ""


def test_mixed_mode_file_rejected(tmp_path, capsys):
    import subprocess
    import json

    lines = [
        {"title": "Snap", "snapshot_url": "http://127.0.0.1:8765/A.html", "url": "http://x"},
        {"title": "Text", "text": "Body", "url": "http://y"},
    ]
    f = tmp_path / "mixed.jsonl"
    f.write_text("\n".join(json.dumps(l) for l in lines), encoding="utf-8")

    r = subprocess.run(
        [sys.executable, "import_tasks.py", "--file", str(f), "--title", "nope"],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True, text=True,
    )
    assert "mixed modes" in r.stdout + r.stderr
    # must fail before touching Django/the project: exit via SystemExit message
    assert "project 'nope' not found" not in r.stdout
