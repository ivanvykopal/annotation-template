import json
from pathlib import Path

import pytest

from normalize_export import normalize

DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture
def export():
    with open(DATA_DIR / "synthetic_export.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mapping():
    return {
        "sk": {
            "Anonymný autor": "choice_autor_anonymny",
            "Neznámy autor": "choice_autor_neznamy",
            "Dezinformácia": "choice_obsah_dez",
        }
    }


def test_normalize_replaces_choices_values(export, mapping):
    out = normalize(export, mapping)
    result = out["tasks"][0]["annotations"][0]["result"]
    assert result[0]["value"]["choices"] == [
        "choice_autor_anonymny",
        "choice_obsah_dez",
    ]


def test_normalize_replaces_scalar_choice_value(export, mapping):
    out = normalize(export, mapping)
    result = out["tasks"][0]["annotations"][0]["result"]
    assert result[1]["value"]["choice"] == "choice_autor_neznamy"


def test_unknown_values_pass_through_and_collected(export, mapping):
    out = normalize(export, mapping)
    choices = out["tasks"][1]["annotations"][0]["result"][0]["value"]["choices"]
    assert choices == ["choice_autor_anonymny", "Unknown Label"]
    assert out["unknown_values"] == ["Unknown Label"]


def test_input_export_not_mutated(export, mapping):
    original = json.dumps(export, ensure_ascii=False)
    normalize(export, mapping)
    assert json.dumps(export, ensure_ascii=False) == original


def test_mapping_lang_prefix_is_optional(export):
    flat = {
        "Anonymný autor": "choice_autor_anonymny",
        "Neznámy autor": "choice_autor_neznamy",
        "Dezinformácia": "choice_obsah_dez",
    }
    out = normalize(export, flat)
    result = out["tasks"][0]["annotations"][0]["result"]
    assert result[0]["value"]["choices"] == [
        "choice_autor_anonymny",
        "choice_obsah_dez",
    ]


def test_no_annotations_and_empty_result_entries_survive(mapping):
    out = normalize(
        [{"id": 3, "annotations": []}, {"id": 4, "annotations": [{"result": []}]}],
        mapping,
    )
    assert out["unknown_values"] == []
    assert out["tasks"][1]["annotations"][0]["result"] == []


def test_cli_end_to_end(tmp_path):
    import subprocess
    import sys

    export_path = DATA_DIR / "synthetic_export.json"
    mapping_path = tmp_path / "mapping.json"
    out_path = tmp_path / "normalized.json"
    mapping_path.write_text(
        json.dumps(
            {
                "sk": {
                    "Anonymný autor": "choice_autor_anonymny",
                    "Neznámy autor": "choice_autor_neznamy",
                    "Dezinformácia": "choice_obsah_dez",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            "normalize_export.py",
            "--export",
            str(export_path),
            "--mapping",
            str(mapping_path),
            "-o",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(out_path.read_text(encoding="utf-8"))
    result = out["tasks"][0]["annotations"][0]["result"]
    assert result[0]["value"]["choices"] == [
        "choice_autor_anonymny",
        "choice_obsah_dez",
    ]
    assert out["unknown_values"] == ["Unknown Label"]
