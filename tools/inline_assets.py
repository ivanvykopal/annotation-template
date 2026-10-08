"""Make HTML snapshots in a tasks JSONL file self-contained (browser-perf fix).

Frozen UI root cause: every task open fired 10-44 blocking <link rel=stylesheet>
fetches against slow/dead ad-tech and CDN endpoints, plus eager image loads.

Transformations per snapshot:
  1. <base href="{url}"> injected so relative resources resolve to origin.
  2. Every external stylesheet is fetched ONCE (cached per URL across pages)
     and inlined as <style>. Failed sheets are dropped silently.
  3. Remaining <link> tags (preload/dns-prefetch/icon/manifest) removed -
     they only trigger hover connects.
  4. <img> gets loading="lazy" decoding="async".
  5. HTML comments and whitespace runs stripped.

Run:
    python tools/inline_assets.py --input tasks.sanitized.jsonl --output tasks.inlined.jsonl
"""

import argparse
import concurrent.futures as cf
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")}
# verify=False: several konspiratori-listed outlets serve broken/legacy TLS chains.
CSS_CAP_BYTES = 500_000

LINK_RE = re.compile(r"<link\b[^>]*?/?>", re.I | re.S)
REL_CSS_RE = re.compile(r'rel\s*=\s*["\']?stylesheet', re.I)
HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
IMG_RE = re.compile(r"<img\b(?![^>]*\b(?:loading|decoding)=)", re.I)
COMMENT_RE = re.compile(r"<!--(?!\[if)[\s\S]*?-->")


def fetch_css(url: str) -> str | None:
    try:
        # verify=False: corpus includes konspiratori-listed outlets with broken
        # TLS chains; validation would silently empty their stylesheets.
        r = requests.get(url, headers=UA, timeout=15, verify=False, stream=True)
        if r.status_code != 200:
            return None
        raw = r.raw.read(CSS_CAP_BYTES, decode_content=True)
        css = raw.decode(r.encoding or "utf-8", errors="replace")
        return css.replace("</style", "<\\/style")
    except Exception:
        return None


def process(html: str, page_url: str, css_cache: dict[str, str | None]) -> str:
    def inline(match: re.Match) -> str:
        tag = match.group(0)
        if not REL_CSS_RE.search(tag):
            return ""  # drop preload/icon/manifest links entirely
        href_m = HREF_RE.search(tag)
        if not href_m:
            return ""
        u = urljoin(page_url, href_m.group(1))
        css = css_cache.get(u)
        if css is None and u not in css_cache:
            return ""  # sheet unfetchable: drop
        return f"<style>{css or ''}</style>"

    html = LINK_RE.sub(inline, html)
    if f'<base href="{page_url}"' not in html:
        html = re.sub(r"<head(\s[^>]*)?>", lambda m: m.group(0) + f'<base href="{page_url}">',
                      html, count=1, flags=re.I)
    html = IMG_RE.sub('<img loading="lazy" decoding="async"', html)
    html = COMMENT_RE.sub("", html)
    return re.sub(r"[^\S\n]{2,}", " ", html)


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
                        help="tasks JSONL to write with inlined assets")
    args = parser.parse_args()

    tasks = load_tasks(args.input)

    # 1) collect every stylesheet URL first, fetch in parallel with a shared cache
    all_urls: set[str] = set()
    per_task: list[tuple[Any, str, list[str]]] = []
    for t in tasks:
        html = t.get("html") or ""
        page_url = t.get("url") or ""
        links = LINK_RE.findall(html)
        urls = [urljoin(page_url, m.group(1))
                for tag in links if REL_CSS_RE.search(tag)
                for m in [HREF_RE.search(tag)] if m]
        per_task.append((t, page_url, urls))
        all_urls.update(urls)
    print(f"unique stylesheets to fetch: {len(all_urls)}")

    cache: dict[str, str | None] = {}
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for u, css in zip(all_urls, ex.map(fetch_css, all_urls), strict=False):
            cache[u] = css
    fetched = sum(v is not None for v in cache.values())
    print(f"fetched {fetched}/{len(all_urls)} stylesheets")

    before = after = 0
    for t, page_url, _urls in per_task:
        html = t.get("html")
        if not html:
            continue
        before += len(html)
        t["html"] = process(html, page_url, cache)
        after += len(t["html"])
    print(f"total: {before / 1e6:.1f} MB -> {after / 1e6:.1f} MB")
    write_tasks(args.output, tasks)
    print("DONE")


if __name__ == "__main__":
    main()
