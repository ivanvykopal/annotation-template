"""Convert a Label Studio annotation export to the final CSV dataset.

Input: Label Studio JSON export (list of tasks with ``data`` and
``annotations`` fields). Label values are resolved to canonical keys via
``build/value_mapping.json`` (any language built by build.py), then mapped
to the binary label — this works for any language pack, unlike a hardcoded
translation lookup.

Label mapping (canonical keys of the "obsah" question):
    choice_obsah_doverihodna -> credible
    choice_obsah_dez          -> disinfo
    choice_obsah_tazko / choice_obsah_nezdochne -> skipped (no binary label)

If a task has several completed, non-cancelled annotations, the most recent
one wins; conflicting decisions are reported.

Task data extra fields used (all optional): ``article_id`` (fallback:
``task<id>``), ``published`` (-> article_publication_date), ``language``
(overrides --language for that task). Snapshot-mode tasks have no ``text``,
so article_body/content are title-only for them.

Usage:
    python export_to_csv.py export.json
    python export_to_csv.py export.json --language pl -o dataset.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

LABEL_MAP = {
    "choice_obsah_doverihodna": "credible",
    "choice_obsah_dez": "disinfo",
}
INDECISIVE_KEYS = {"choice_obsah_tazko", "choice_obsah_nezdochne"}

COLUMNS = [
    "article_id",
    "article_publication_date",
    "article_title",
    "article_url",
    "article_body",
    "content",
    "label",
    "language",
]


def flatten_mapping(value_mapping: dict) -> dict[str, str]:
    """{lang: {rendered_value: key}} -> {rendered_value: key}."""
    flat: dict[str, str] = {}
    for _, lang_map in (value_mapping or {}).items():
        flat.update(lang_map or {})
    return flat


def decision(annotation: dict, flat: dict[str, str]) -> tuple[str | None, str]:
    """(canonical key, raw value) of the 'obsah' choice; (None, raw) if none."""
    for r in annotation.get("result") or []:
        if r.get("from_name") != "obsah":
            continue
        choices = (r.get("value") or {}).get("choices") or []
        raw = choices[0] if choices else ""  # single-choice question
        return flat.get(raw), raw
    return None, ""


def task_row(task: dict, flat: dict[str, str], language: str,
             stats: dict[str, int]) -> tuple[dict | None, str]:
    """Row for one task, or (None, reason) if it yields no binary label."""
    data = task.get("data") or {}
    anns = [
        a for a in (task.get("annotations") or [])
        if not a.get("was_cancelled") and a.get("result")
    ]
    if not anns:
        return None, "no_annotation"

    resolved = [decision(a, flat) for a in anns]
    keys = {key for key, _ in resolved if key is not None}
    # most recently updated completed annotation wins
    order = sorted(range(len(anns)),
                   key=lambda i: anns[i].get("updated_at")
                   or anns[i].get("created_at") or "")
    key, raw = resolved[order[-1]]
    if len(keys) > 1:
        stats["conflict"] = stats.get("conflict", 0) + 1
        print(f"[warn] {data.get('article_id')}: conflicting annotations "
              f"{keys}; using most recent -> {key} (raw: {raw!r})")
    if key is None:
        if raw and raw not in flat:
            return None, "unmapped"
        return None, "indecisive"
    if key in INDECISIVE_KEYS:
        return None, "indecisive"
    label = LABEL_MAP.get(key)
    if label is None:  # an obsah key we do not binary-map (future additions)
        return None, "unmapped"

    article_id = str(data.get("article_id") or f"task{task.get('id')}")
    title = data.get("title") or ""
    body = data.get("text") or ""
    return {
        "article_id": article_id,
        "article_publication_date": data.get("published") or "",
        "article_title": title,
        "article_url": data.get("url") or "",
        "article_body": body,
        "content": f"{title}\n\n{body}".strip(),
        "label": label,
        "language": data.get("language") or language or "",
    }, ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export", type=Path, help="Label Studio JSON export file")
    ap.add_argument("--mapping", type=Path,
                    default=HERE / "build" / "value_mapping.json",
                    help="value mapping from build.py (default: %(default)s)")
    ap.add_argument("--language", default="",
                    help="language tag for all rows (e.g. pl, en); "
                         "overridden per task by a 'language' data field")
    ap.add_argument("-o", "--out", type=Path, default=HERE / "annotations.csv",
                    help="output CSV (default: %(default)s)")
    args = ap.parse_args()

    try:
        tasks = json.loads(args.export.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"missing/invalid export file: {e}") from e
    # tolerate {"tasks": [...]} wrapper
    if isinstance(tasks, dict):
        tasks = tasks.get("tasks") or []

    try:
        flat = flatten_mapping(json.loads(args.mapping.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(
            f"missing/invalid mapping {args.mapping}: run build.py first ({e})"
        ) from e

    stats: dict[str, int] = {}
    reasons: dict[str, int] = {}
    rows = []
    for t in tasks:
        row, reason = task_row(t, flat, args.language, stats)
        if row is not None:
            rows.append(row)
        else:
            reasons[reason] = reasons.get(reason, 0) + 1

    try:
        with args.out.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rows)
    except OSError as e:
        raise SystemExit(f"cannot write {args.out}: {e}") from e

    print(f"tasks: {len(tasks)} | rows written: {len(rows)} -> {args.out}")
    skipped = ", ".join(f"{n} {r}" for r, n in sorted(reasons.items()))
    if skipped or stats.get("conflict"):
        parts = [f"skipped: {skipped}" if skipped else ""]
        if stats.get("conflict"):
            parts.append(f"conflicts: {stats['conflict']}")
        print(" | ".join(p for p in parts if p), file=sys.stderr)


if __name__ == "__main__":
    main()
