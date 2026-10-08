"""Snapshot article webpages into task data (offline embedding).

Reads a tasks JSONL file (one flat task-data object per line, the same
shape import_tasks.py imports), fetches the page of every task that has no
"html" field yet, and writes the enriched tasks to the output JSONL. The
frontend HyperText can then render $html inline - no iframe/
X-Frame-Options problems. Tasks whose page fails to download keep their
other fields unchanged (the extracted text stays the only content - the
fallback contract of the labeling config).

Run:
    python tools/embed_pages.py --input tasks.jsonl --output tasks.embedded.jsonl
"""

import argparse
import concurrent.futures as cf
import json
import time
from pathlib import Path

import requests

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sk-SK,sk;q=0.9,en;q=0.7",
}
# verify=False: several konspiratori-listed outlets serve broken/legacy TLS
# chains; certificate validation would exclude them from the corpus.


def snapshot(url: str) -> str | None:
    time.sleep(0.3)
    try:
        r = requests.get(url, headers=UA, timeout=25, verify=False)
        if r.status_code != 200 or not r.content:
            return None
        text = r.content.decode(r.encoding or "utf-8", errors="replace")
        return text if "html" in text[:2000].lower() else None
    except Exception:
        return None


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
                        help="tasks JSONL to read (flat task-data objects)")
    parser.add_argument("--output", type=Path, required=True,
                        help="tasks JSONL to write with embedded html")
    args = parser.parse_args()

    tasks = load_tasks(args.input)
    todo = [t for t in tasks if not t.get("html")]
    print(f"tasks: {len(tasks)}, to snapshot: {len(todo)}")

    def work(task):
        url = task.get("meta_url") or task.get("url") or ""
        html = snapshot(url) if url else None
        if html:
            task["html"] = html
        return bool(html)

    ok = 0
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for i, success in enumerate(ex.map(work, todo), 1):
            ok += success
            if i % 20 == 0:
                print(f"  {i}/{len(todo)} done ({ok} snapshots)")
    print(f"snapshots stored: {ok}/{len(todo)}; fallback-only tasks: {len(todo) - ok}")
    write_tasks(args.output, tasks)
    print("DONE")


if __name__ == "__main__":
    main()
