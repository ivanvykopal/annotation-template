"""Externalize HTML snapshots from a tasks JSONL file to disk.

Moves the "html" field out of every task (raw snapshots make the tasks JSONL
carry megabytes per page), writes it to <snapshot-dir>/<article_id>.html,
and stores snapshot_url = <base-url>/<article_id>.html instead. HyperText
with valueType="url" then fetches the page only when the record is opened.

Run:
    python tools/externalize_snapshots.py --input tasks.inlined.jsonl --output tasks.final.jsonl
"""

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAP_DIR = HERE.parent / "snapshots"
SNAP_BASE = "http://127.0.0.1:8765"


def load_tasks(path: Path) -> list[dict]:
    tasks: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))
    return tasks


def write_tasks(path: Path, tasks: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="tasks JSONL to read (tasks with html fields)")
    parser.add_argument("--output", type=Path, required=True,
                        help="tasks JSONL to write with snapshot_url instead of html")
    parser.add_argument("--snapshot-dir", type=Path, default=SNAP_DIR,
                        help=f"directory to write <article_id>.html files to "
                             f"(default: {SNAP_DIR})")
    parser.add_argument("--base-url", default=SNAP_BASE,
                        help=f"base URL for snapshot_url values (default: {SNAP_BASE})")
    args = parser.parse_args()

    args.snapshot_dir.mkdir(exist_ok=True)
    tasks = load_tasks(args.input)
    out: list[dict] = []
    before = after = written = already = 0
    for i, task in enumerate(tasks, start=1):
        data = dict(task)
        html = data.pop("html", None)
        aid = data.get("article_id") or f"task{i}"
        try:
            if html:
                (args.snapshot_dir / f"{aid}.html").write_text(html, encoding="utf-8")
                before += len(html)
                written += 1
            elif (args.snapshot_dir / f"{aid}.html").exists():
                already += 1
            else:
                print(f"  [warn] {aid}: no html anywhere")
                out.append(task)  # task keeps its html, snapshot_url not set
                continue
        except OSError as e:
            raise SystemExit(f"cannot write snapshot for {aid}: {e}") from e
        data["snapshot_url"] = f"{args.base_url}/{aid}.html"
        out.append(data)
        after += len(str(data))
    print(f"snapshots written: {written}, already on disk: {already}")
    print(f"moved out of db: {before / 1e6:.1f} MB | task data now total: {after / 1e6:.2f} MB")
    write_tasks(args.output, out)
    print("DONE")


if __name__ == "__main__":
    main()
