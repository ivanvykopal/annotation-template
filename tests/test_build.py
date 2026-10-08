"""Tests for the annotation-template config renderer (build.py)."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

import build

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = (ROOT / "config.template.xml").read_text(encoding="utf-8")
STRINGS = yaml.safe_load((ROOT / "languages" / "sk" / "strings.yaml").read_text(encoding="utf-8"))


def render(mode="binary", text_mode=False, strings=None):
    return build.render(TEMPLATE, STRINGS if strings is None else strings, mode, text_mode)


def test_binary_snapshot_render():
    """(a) binary snapshot render: no placeholders left, valid XML, no FULL-mode keys."""
    out = render(mode="binary", text_mode=False)
    assert "{{" not in out, "unresolved placeholders remain"
    ET.fromstring(out)
    full_only_keys = re.findall(r"{{#FULL}}(.*?){{/FULL}}", TEMPLATE, re.DOTALL)
    for block in full_only_keys:
        for key in re.findall(r"{{(\w+)}}", block):
            if key == "target":
                continue
            assert "{{" + key not in out
    assert 'name="web"' in out
    assert "$snapshot_url" in out
    # BINARY banner kept
    assert 'name="done_dez"' in out


def test_full_render_contains_step2_block():
    """(b) full render keeps FULL block; whenChoiceValue refs match rendered Choice values."""
    out = render(mode="full", text_mode=False)
    ET.fromstring(out)
    assert 'whenChoiceValue="{{choice_obsah_dez}}"' not in out
    choice_values = set()
    when_values = set()
    for m in re.finditer(r'<Choice value="([^"]*)"', out):
        choice_values.add(m.group(1))
    for m in re.finditer(r'whenChoiceValue="([^"]*)"', out):
        when_values.add(m.group(1))
    assert choice_values, "no choices rendered"
    assert when_values <= choice_values, (
        f"whenChoiceValue(s) without matching Choice: {sorted(when_values - choice_values)}"
    )
    # Step 2 block (krok 2) present in full mode
    assert "2.1" in out


def test_text_mode_render():
    """(c) text mode: name=\"text\", no HyperText."""
    out = render(mode="binary", text_mode=True)
    ET.fromstring(out)
    assert '<Text name="text" value="$text"/>' in out
    assert "HyperText" not in out


def test_missing_key_raises_build_error():
    """(d) missing key -> BuildError naming the key."""
    strings = dict(STRINGS)
    del strings["title_clanok"]
    with pytest.raises(build.BuildError) as excinfo:
        build.render(TEMPLATE, strings, "binary", False)
    assert "title_clanok" in str(excinfo.value)


def test_value_xml_escaped():
    """(e) value with XML special chars is escaped."""
    out = render(
        strings={**STRINGS, "title_clanok": "Tom & Jerry"}
    )
    assert "Tom &amp; Jerry" in out
    ET.fromstring(out)


def test_value_mapping_covers_rendered_choices():
    """(f) rendered Choice values == mapping keys, both directions (full render)."""
    out = render(mode="full", text_mode=False)
    mapping = build.build_value_mapping(STRINGS)
    rendered = set(re.findall(r'<Choice value="([^"]*)"', out))
    mapped = set(mapping)
    assert rendered == mapped, (
        f"only in rendered: {sorted(rendered - mapped)}; "
        f"only in mapping: {sorted(mapped - rendered)}"
    )
    # reverse: rendered value maps back to the canonical key
    for value, key in mapping.items():
        assert STRINGS[key] == html_unescape(value)


def test_value_mapping_superset_of_binary_render_choices():
    """Binary (snapshot) render's choices are all covered by the mapping."""
    out = render(mode="binary", text_mode=False)
    mapping = build.build_value_mapping(STRINGS)
    rendered = set(re.findall(r'<Choice value="([^"]*)"', out))
    assert rendered <= set(mapping)


def html_unescape(s):
    import html

    return html.unescape(s)
