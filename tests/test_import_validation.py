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
