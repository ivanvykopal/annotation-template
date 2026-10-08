"""Tests for export_to_csv.py (pure functions, no Django needed)."""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from export_to_csv import COLUMNS, flatten_mapping, task_row

MAPPING = {"sk": {
    "Dôveryhodná informácia": "choice_obsah_doverihodna",
    "Dezinformácia": "choice_obsah_dez",
    "Ťažko povedať": "choice_obsah_tazko",
    "Nezhodné s témou": "choice_obsah_nezdochne",
}}

FLAT = flatten_mapping(MAPPING)


def _task(anns, data=None):
    return {"id": 7, "data": data if data is not None else {
        "article_id": "A1", "title": "Title", "url": "http://x",
        "text": "Body text", "published": "2026-01-02",
    }, "annotations": anns}


def _ann(choice, updated="2026-01-01T10:00:00Z", cancelled=False):
    return {"was_cancelled": cancelled, "updated_at": updated, "result": [
        {"from_name": "obsah", "value": {"choices": [choice]}}]}


def test_columns_exact():
    assert COLUMNS == ["article_id", "article_publication_date", "article_title",
                       "article_url", "article_body", "content", "label", "language"]


def test_credible_row():
    row, _ = task_row(_task([_ann("Dôveryhodná informácia")]), FLAT, "pl", {})
    assert row["label"] == "credible"
    assert row["language"] == "pl"
    assert row["content"] == "Title\n\nBody text"
    assert row["article_publication_date"] == "2026-01-02"
    assert row["article_body"] == "Body text"


def test_disinfo_row():
    row, _ = task_row(_task([_ann("Dezinformácia")]), FLAT, "en", {})
    assert row["label"] == "disinfo"


def test_indecisive_skipped():
    for choice in ("Ťažko povedať", "Nezhodné s témou"):
        row, reason = task_row(_task([_ann(choice)]), FLAT, "pl", {})
        assert row is None and reason == "indecisive"


def test_unmapped_choice_skipped_with_reason():
    row, reason = task_row(_task([_ann("Something unknown")]), FLAT, "pl", {})
    assert row is None and reason == "unmapped"


def test_no_completed_annotation_skipped():
    row, reason = task_row(_task([_ann("Dezinformácia", cancelled=True)]), FLAT, "pl", {})
    assert row is None and reason == "no_annotation"


def test_most_recent_wins_with_conflict_stat():
    task = _task([_ann("Dôveryhodná informácia", "2026-01-01T10:00:00Z"),
                  _ann("Dezinformácia", "2026-02-01T10:00:00Z")])
    stats = {}
    row, _ = task_row(task, FLAT, "pl", stats)
    assert row["label"] == "disinfo"
    assert stats.get("conflict") == 1


def test_language_from_task_data_overrides_cli():
    data = {"title": "T", "url": "http://x", "text": "B", "language": "cs"}
    row, _ = task_row(_task([_ann("Dezinformácia")], data), FLAT, "pl", {})
    assert row["language"] == "cs"


def test_defaults_when_fields_missing():
    data = {"title": "T"}
    row, _ = task_row(_task([_ann("Dezinformácia")], data), FLAT, "", {})
    assert row["article_id"] == "task7"
    assert row["article_url"] == "" and row["article_body"] == ""
    assert row["language"] == "" and row["article_publication_date"] == ""
    assert row["content"] == "T"


def test_flatten_mapping_all_languages():
    assert flatten_mapping({"sk": {"A": "k1"}, "cs": {"B": "k2"}}) == {"A": "k1", "B": "k2"}


def test_cli_end_to_end(tmp_path):
    import subprocess
    export = tmp_path / "export.json"
    export.write_text(json.dumps([
        _task([_ann("Dôveryhodná informácia")]),
        _task([_ann("Ťažko povedať")], {"article_id": "A2", "title": "X", "url": "u", "text": "b"}),
    ]), encoding="utf-8")
    mapping = tmp_path / "value_mapping.json"
    mapping.write_text(json.dumps(MAPPING), encoding="utf-8")
    out = tmp_path / "dataset.csv"
    r = subprocess.run(
        [sys.executable, "export_to_csv.py", str(export),
         "--mapping", str(mapping), "--language", "pl", "-o", str(out)],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    rows = list(csv.DictReader(out.open(encoding="utf-8-sig")))
    assert len(rows) == 1 and rows[0]["label"] == "credible" and rows[0]["language"] == "pl"
    assert "skipped: 1 indecisive" in r.stderr
