"""Sanitize HTML snapshots stored in a tasks JSONL file.

Raw page HTML (scripts, ad iframes, autoplay video) freezes the annotation
UI when HyperText renders it. Strip executable/embed-heavy elements while
preserving layout, styles and images, so the page still looks like the
original webpage.

Run:
    python tools/sanitize_snapshots.py --input tasks.embedded.jsonl --output tasks.sanitized.jsonl
"""

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path

# stdlib-only stripper: no extra packages needed just for this
class _Stripper(HTMLParser):
    DROP = {"script", "iframe", "video", "audio", "object", "embed", "noscript",
            "template", "canvas"}
    VOID = {"br", "img", "hr", "meta", "link", "input", "source", "wbr", "col"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.skip: list[str] = []

    def _emit_attrs(self, attrs: list[tuple[str, str | None]]) -> str:
        parts = []
        for k, v in attrs:
            if k.lower().startswith("on"):  # onclick & friends
                continue
            parts.append(f'{k}="{v.replace(chr(34), "&quot;")}"' if v is not None else k)
        return (" " + " ".join(parts)) if parts else ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.DROP:
            self.skip.append(tag)
            return
        if self.skip:
            return
        self.out.append(f"<{tag}{self._emit_attrs(attrs)}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.DROP or self.skip:
            return
        self.out.append(f"<{tag}{self._emit_attrs(attrs)}/>")

    def handle_endtag(self, tag: str) -> None:
        if self.skip:
            if tag == self.skip[-1]:
                self.skip.pop()
            return
        if tag in self.DROP or tag in self.VOID:
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.out.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self.skip:
            self.out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self.skip:
            self.out.append(f"&#{name};")


def sanitize(html: str) -> str:
    p = _Stripper()
    try:
        p.feed(html)
        p.close()
        return "".join(p.out)
    except Exception:
        return html  # malformed beyond html.parser: keep original rather than lose it


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
                        help="tasks JSONL to write with sanitized html")
    args = parser.parse_args()

    tasks = load_tasks(args.input)
    total_before = total_after = done = 0
    for t in tasks:
        html = t.get("html")
        if not html:
            continue
        cleaned = sanitize(html)
        total_before += len(html)
        total_after += len(cleaned)
        t["html"] = cleaned
        done += 1
    print(f"sanitized {done} tasks: {total_before / 1e6:.1f} MB -> {total_after / 1e6:.1f} MB")
    write_tasks(args.output, tasks)
    print("DONE")


if __name__ == "__main__":
    main()
