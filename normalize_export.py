#!/usr/bin/env python
"""Normalize Label Studio JSON exports.

Replaces Choices result values (``value.choices`` lists and ``value.choice``
scalars) with canonical choice keys using the value mapping produced by
``build.py`` (``build/value_mapping.json``, shape ``{"<lang>": {rendered_value: key}}``).
Values not present in the mapping pass through unchanged and are collected in
the ``unknown_values`` list of the returned structure.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys

RESULT_TYPES = {"choices", "choice"}


def _flatten_mapping(mapping: dict) -> dict:
    """Flatten ``{"<lang>": {value: key}}`` (or a flat ``{value: key}``) to one lookup."""
    flat = {}
    for key, value in mapping.items():
        if isinstance(value, dict):
            for rendered, canonical in value.items():
                if rendered in flat and flat[rendered] != canonical:
                    # Cross-language collision: the same rendered value maps
                    # to different keys in different languages. Last wins.
                    print(
                        f"warning: value {rendered!r} maps to both "
                        f"{flat[rendered]!r} and {canonical!r}; using {canonical!r} (last wins)",
                        file=sys.stderr,
                    )
                flat[rendered] = canonical
        else:
            flat[key] = value
    return flat


def normalize(export, mapping: dict) -> dict:
    """Normalize a Label Studio export.

    ``export`` is the parsed export JSON (a list of task objects).
    ``mapping`` is either ``{"<lang>": {rendered_value: key}}`` or a flat
    ``{rendered_value: key}`` dict.

    Returns ``{"tasks": <normalized export>, "unknown_values": [...]}``.
    The input export is not mutated.
    """
    lookup = _flatten_mapping(mapping)
    tasks = copy.deepcopy(export)
    unknown_values = []

    for task in tasks:
        for annotation in task.get("annotations", []) or []:
            for entry in annotation.get("result", []) or []:
                if (entry.get("type") or "").lower() not in RESULT_TYPES:
                    continue
                value = entry.get("value")
                if not isinstance(value, dict):
                    continue
                choices = value.get("choices")
                if isinstance(choices, list):
                    value["choices"] = [
                        _map_choice(c, lookup, unknown_values) for c in choices
                    ]
                if "choice" in value:
                    value["choice"] = _map_choice(
                        value["choice"], lookup, unknown_values
                    )
    return {"tasks": tasks, "unknown_values": sorted({str(v) for v in unknown_values})}


def _map_choice(choice, lookup: dict, unknown_values: list):
    if isinstance(choice, str) and choice in lookup:
        return lookup[choice]
    if choice not in unknown_values:
        unknown_values.append(choice)
    return choice


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", required=True, help="Label Studio export JSON")
    parser.add_argument(
        "--mapping", required=True, help="value mapping JSON (build/value_mapping.json)"
    )
    parser.add_argument("-o", "--output", required=True, help="output JSON path")
    args = parser.parse_args(argv)

    with open(args.export, encoding="utf-8") as f:
        export = json.load(f)
    with open(args.mapping, encoding="utf-8") as f:
        mapping = json.load(f)

    result = normalize(export, mapping)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"wrote {args.output}")
    if result["unknown_values"]:
        print(
            f"warning: {len(result['unknown_values'])} unknown value(s) passed through:",
            file=sys.stderr,
        )
        for value in result["unknown_values"]:
            print(f"  {value!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
