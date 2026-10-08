#!/usr/bin/env python
"""Render a Label Studio labeling config from a language pack.

Usage:
    python build.py --language sk [--mode binary|full] [--text]

Consumes  config.template.xml, languages/<lang>/strings.yaml,
          languages/<lang>/guidelines.html
Produces  build/labeling_config.xml, build/guidelines.html,
          build/value_mapping.json  ({"<lang>": {rendered_value: key}})
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent

MARKER_BLOCKS = ("FULL", "BINARY", "SNAPSHOT", "TEXT")


class BuildError(Exception):
    """Raised when the template cannot be rendered into a valid config."""


def _strip_block(text: str, marker: str) -> str:
    """Remove {{#MARKER}}...{{/MARKER}} blocks (including the marker lines)."""
    pattern = re.compile(
        r"[ \t]*\{\{#" + marker + r"\}\}[^\n]*\n.*?\{\{/" + marker + r"\}\}[ \t]*\n?",
        re.DOTALL,
    )
    return pattern.sub("", text)


def _strip_marker_line(text: str, marker: str) -> str:
    """Remove bare {{#MARKER}} / {{/MARKER}} lines left by nesting."""
    pattern = re.compile(r"[ \t]*\{\{#" + marker + r"\}\}[ \t]*\n|[ \t]*\{\{/" + marker + r"\}\}[ \t]*\n")
    return pattern.sub("", text)


def render(template: str, strings: dict, mode: str, text_mode: bool) -> str:
    """Render the template with the given strings and mode flags."""
    if mode not in ("binary", "full"):
        raise BuildError(f"unknown mode: {mode!r}")

    text = template
    # Mode blocks.
    if mode != "full":
        text = _strip_block(text, "FULL")
    if mode == "full":
        text = _strip_block(text, "BINARY")
    # Snapshot vs text mode.
    if text_mode:
        text = _strip_block(text, "SNAPSHOT")
    else:
        text = _strip_block(text, "TEXT")

    # Any leftover bare marker lines from nested blocks.
    for marker in MARKER_BLOCKS:
        text = _strip_marker_line(text, marker)

    # Substitute {{target}} first, then all remaining keys in one pass.
    target = "text" if text_mode else "web"
    text = text.replace("{{target}}", target)

    missing = set()

    def _sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in strings:
            missing.add(key)
            return m.group(0)
        return html.escape(str(strings[key]), quote=True)

    text = re.sub(r"\{\{(\w+)\}\}", _sub, text)
    if missing:
        raise BuildError("missing keys: " + ", ".join(sorted(missing)))

    try:
        ET.fromstring(text)
    except ET.ParseError as e:
        raise BuildError(f"rendered XML does not parse: {e}") from e

    return text


def build_value_mapping(strings: dict) -> dict:
    """Map raw (unescaped) choice values back to canonical YAML keys.

    Label Studio exports the UNescaped label text, so the mapping must be
    keyed by the raw YAML value, not the XML-escaped form that appears in
    the rendered labeling config.
    """
    mapping = {}
    for key, value in strings.items():
        if key.startswith("choice_"):
            mapping[str(value)] = key
    return mapping


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", required=True, help="language code, e.g. sk")
    parser.add_argument("--mode", choices=["binary", "full"], default="binary")
    parser.add_argument("--text", action="store_true", help="render for text (no web snapshot) mode")
    args = parser.parse_args(argv)

    lang_dir = ROOT / "languages" / args.language
    try:
        template = (ROOT / "config.template.xml").read_text(encoding="utf-8")
        strings = yaml.safe_load((lang_dir / "strings.yaml").read_text(encoding="utf-8"))
        guidelines = (lang_dir / "guidelines.html").read_text(encoding="utf-8")
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    try:
        rendered = render(template, strings, args.mode, args.text)
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    out_dir = ROOT / "build"
    out_dir.mkdir(exist_ok=True)

    # Accumulate mappings across languages: merge this language's mapping
    # into any existing build/value_mapping.json so researchers who build
    # several languages keep a combined mapping for normalize_export.py.
    mapping_path = out_dir / "value_mapping.json"
    combined = {}
    if mapping_path.exists():
        try:
            combined = json.loads(mapping_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"error: cannot read existing {mapping_path}: {e}", file=sys.stderr)
            return 1
    if not isinstance(combined, dict):
        print(f"error: {mapping_path} is not a JSON object", file=sys.stderr)
        return 1
    combined[args.language] = build_value_mapping(strings)

    (out_dir / "labeling_config.xml").write_text(rendered, encoding="utf-8")
    (out_dir / "guidelines.html").write_text(guidelines, encoding="utf-8")
    mapping_path.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {out_dir / 'labeling_config.xml'} ({args.language}, mode={args.mode}, text_mode={args.text})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
