# Snapshot pipeline: raw article HTML → served snapshot

Snapshot-mode tasks embed the article via
`<HyperText name="web" value="$snapshot_url" valueType="url">`. This document
describes how raw article HTML is turned into the snapshot files that
`cors_server.py` serves from `snapshots/`.

## Why a pipeline

- **Inline raw HTML froze the annotation UI.** Embedded pages fired dozens of
  blocking stylesheet fetches against slow/dead ad-tech endpoints, and
  scripts/iframes autoplaying video hung the tab.
- **Page fetches broke in the browser.** Loading articles directly in an
  iframe hits `X-Frame-Options` refusals; fetching them from the Label Studio
  page hits CORS — hence snapshots are fetched once, offline, by the pipeline
  and served by our own CORS-enabled server.
- **Full HTML in task data bloated the database.** Megabytes per page moved
  into every task row; externalization keeps only a URL in the task and the
  file on disk.

## The chain

All four tools are standalone scripts with the same `--input/--output`
JSONL interface (run from the repo root; `requests` required for the two
fetching tools):

```
tasks.in.jsonl
   └─ tools/embed_pages.py           fetch raw HTML for tasks without "html"
tasks.embedded.jsonl
   └─ tools/sanitize_snapshots.py    strip scripts, iframes, media, on* attrs
tasks.sanitized.jsonl
   └─ tools/inline_assets.py         inline stylesheets, inject <base>, lazy imgs
tasks.inlined.jsonl
   └─ tools/externalize_snapshots.py write snapshots/<article_id>.html, set snapshot_url
tasks.final.jsonl  (+ snapshots/<article_id>.html served by cors_server.py)
```

The input is the same flat task-data JSONL shape `import_tasks.py` consumes
(see [DATA.md](DATA.md)). Each task needs a `url` (used to fetch the page and
to resolve relative resources) and — for stable snapshot filenames — an
`article_id`. The final output has `snapshot_url` and no `html`, and is
directly importable.

Example run (verified end-to-end; the second task's page was served from a
local test server):

```bash
python tools/embed_pages.py           --input tasks.in.jsonl        --output tasks.embedded.jsonl
# tasks: 2, to snapshot: 1
# snapshots stored: 1/1; fallback-only tasks: 0

python tools/sanitize_snapshots.py   --input tasks.embedded.jsonl  --output tasks.sanitized.jsonl
# sanitized 2 tasks: 0.9 MB -> 0.9 MB

python tools/inline_assets.py        --input tasks.sanitized.jsonl --output tasks.inlined.jsonl
# unique stylesheets to fetch: 1
# fetched 1/1 stylesheets
# total: 0.9 MB -> 0.9 MB

python tools/externalize_snapshots.py --input tasks.inlined.jsonl --output tasks.final.jsonl
# snapshots written: 2, already on disk: 0
# moved out of db: 0.9 MB | task data now total: 0.00 MB
```

## Tool by tool

### `tools/embed_pages.py` — fetch the raw pages

```bash
python tools/embed_pages.py --input tasks.in.jsonl --output tasks.embedded.jsonl
```

For every task that has no `html` field yet, fetches the page — from
`meta_url` if present, else `url` — and stores it as `html`. Tasks that
already have `html` pass through untouched. Downloads run in 6 parallel
workers with a 0.3 s pause each, a 25 s timeout, and a desktop browser
User-Agent. A response only counts if it is HTTP 200, non-empty, and looks
like HTML (`"html"` appears in the first 2000 characters, case-insensitive).
Tasks whose page fails to download keep their other fields unchanged — their
`text` (if any) remains the only content, matching the labeling config's
fallback.

### `tools/sanitize_snapshots.py` — strip executable/embed-heavy content

```bash
python tools/sanitize_snapshots.py --input tasks.embedded.jsonl --output tasks.sanitized.jsonl
```

**Sanitization guarantees.** After this step a snapshot contains:

- **no** `script`, `iframe`, `video`, `audio`, `object`, `embed`, `noscript`,
  `template` or `canvas` elements (including their entire contents);
- **no** `on*` event-handler attributes (`onclick`, `onload`, …);
- everything else preserved: text, structure, styles, images, links.

So an annotator's browser never executes snapshot JavaScript and never loads
third-party frames or media, while the page still looks like the original
article. The parser is stdlib `html.parser` (no extra dependencies); if a
page is malformed beyond what it can process, the **original** HTML is kept
rather than lost.

### `tools/inline_assets.py` — make snapshots self-contained

```bash
python tools/inline_assets.py --input tasks.sanitized.jsonl --output tasks.inlined.jsonl
```

Per snapshot:

1. `<base href="{url}">` is injected into `<head>` (only if no identical base
   exists) so relative image/link URLs still resolve to the origin site;
2. every external stylesheet is fetched **once** (cached across all pages, 8
   parallel workers, 15 s timeout, 500 KB per sheet) and inlined as
   `<style>`; sheets that fail to download are dropped silently;
3. all remaining `<link>` tags (`preload`, `dns-prefetch`, icons, manifests)
   are removed — they only caused background connections;
4. `<img>` tags get `loading="lazy" decoding="async"`;
5. HTML comments and whitespace runs are stripped.

Result: opening a task no longer triggers dozens of blocking network
requests.

### `tools/externalize_snapshots.py` — move snapshots out of task data

```bash
python tools/externalize_snapshots.py --input tasks.inlined.jsonl --output tasks.final.jsonl
```

Pops the `html` field, writes it to `<snapshot-dir>/<article_id>.html`, and
stores `snapshot_url = <base-url>/<article_id>.html` instead. Defaults:
`--snapshot-dir` is the repo's `snapshots/` and `--base-url` is
`http://127.0.0.1:8765` (matching `cors_server.py`). If a task has no
`html` but a file for its `article_id` already exists on disk, the existing
file is reused. Tasks with neither are warned about and passed through
unchanged (no `snapshot_url` set). If `article_id` is missing, the 1-based
line number is used (`task1`, `task2`, …).

## Serving and referencing snapshots

`cors_server.py` serves its root directory (default `snapshots/`) on
`127.0.0.1:8765` with CORS headers for the local Label Studio origins
(ports 8080/8081) — the stock `python -m http.server` sends no CORS headers,
which makes the HyperText `valueType="url"` embeds fail with
`TypeError: Failed to fetch`.

To place a snapshot **manually** (without the pipeline), copy the file into
`snapshots/` and reference it in the task as:

```json
"snapshot_url": "http://127.0.0.1:8765/<filename>.html"
```

then run the server from the repo root:

```bash
python cors_server.py            # or use start.bat / start.sh
```

## Known quirks

- **Windows CRLF**: snapshot files are written with `write_text()` without a
  newline override, so on Windows the served HTML can have CRLF line endings.
  Browsers don't care.
- **Re-running `inline_assets.py`** on an already-processed snapshot whose
  task `url` differs from the existing `<base href>` injects a second
  `<base>` element (the duplicate check compares the URL). Re-run inline only
  on non-processed snapshots, or with the same `url`.
- **`article_id` is used as a filename verbatim** — no path-safety check. Keep
  ids to letters, digits, `-` and `_`, or the write will fail or land
  elsewhere.
- **`verify=False` on TLS** in `embed_pages.py` and `inline_assets.py`:
  several outlets in the corpus serve broken/legacy certificate chains, and
  validation would silently exclude them from the corpus. This accepts the
  usual man-in-the-middle risk of unvalidated HTTPS.
