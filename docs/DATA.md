# Task data and export formats

This document specifies the `tasks.jsonl` format consumed by
`import_tasks.py`, the annotation export produced by Label Studio, and how
`normalize_export.py` maps the two together.

## Task JSONL

One flat JSON object per line, UTF-8. Blank lines are skipped. Invalid lines
are reported with their line number and skipped — one bad line never aborts
the whole import:

```
line 3: missing field 'title' - skipped
line 7: invalid JSON (Expecting ',' delimiter: ...) - skipped
```

### Snapshot mode (default)

```json
{"title": "Poľsko a Rumunsko majú podľa súdu uhradiť nezaplatené vakcíny proti covidu. Ide o stovky miliónov eur", "url": "https://hnonline.sk/svet/96273663-polsko-a-rumunsko-maju-podla-sudu-uhradit-nezaplatene-vakciny-proti-covidu-ide-o-stovky-milionov-eur", "snapshot_url": "http://127.0.0.1:8765/EXAMPLE.html"}
```

| Field | Type | Rules |
|---|---|---|
| `title` | string | required; shown as the article heading in the UI |
| `url` | string | required; the original article URL, shown below the embed |
| `snapshot_url` | string | required; URL of the sanitized snapshot, served by `cors_server.py` |

The article itself is embedded into the annotation UI via
`<HyperText value="$snapshot_url" valueType="url">`. The `cors_server.py`
process must be running and the file must exist under its `--root`
(default `snapshots/`).

### Text mode

```json
{"title": "Príklad článku v textovom režime", "url": "https://example.com/clanok-textovy-rezim", "text": "Vysoké ceny energie v Európe sú podľa virálneho príspevku dôsledkom úmyselnej politiky Bruselu…"}
```

| Field | Type | Rules |
|---|---|---|
| `title` | string | required |
| `url` | string | required |
| `text` | string | required; the article body, rendered as text |

### Validation rules

`import_tasks.py` applies these checks before importing a line:

- the line must be a JSON object;
- `title` must be present and a string;
- `url` must be present;
- exactly one of `snapshot_url` / `text` must be present, and it must be a
  string — providing both is rejected as `conflicting modes: use either
  'snapshot_url' or 'text', not both`.

Any other fields (e.g. `article_id`, `source`) pass through untouched and are
stored as extra task data in Label Studio. The pipeline tools use
`article_id` as the snapshot filename, so keep it unique and path-safe
(letters, digits, `-`, `_`).

Do not mix modes in one file: the labeling config is built for one mode
(`build.py --text` vs. default), and tasks of the other mode will not
display. Both modes are demonstrated in `tasks.example.jsonl`.

## Label Studio annotation export

Export from the Label Studio UI (project → *Export* → **JSON**). The file is
a JSON list with one object per task:

```json
[
  {
    "id": 42,
    "data": {
      "title": "Poľsko a Rumunsko majú podľa súdu uhradiť…",
      "url": "https://hnonline.sk/svet/96273663-…",
      "snapshot_url": "http://127.0.0.1:8765/EXAMPLE.html"
    },
    "annotations": [
      {
        "result": [
          {
            "from_name": "autor",
            "to_name": "web",
            "type": "choices",
            "value": { "choices": ["Neznámy autor"] }
          },
          {
            "from_name": "obsah",
            "to_name": "web",
            "type": "choice",
            "value": { "choice": "Dezinformácia" }
          },
          {
            "from_name": "autor_meno_neznamy",
            "to_name": "web",
            "type": "textarea",
            "value": { "text": ["Jozef Mrkva"] }
          }
        ],
        "was_cancelled": false
      }
    ]
  }
]
```

Field walkthrough:

- `id` — Label Studio's task id.
- `data` — exactly the flat task object that was imported (all fields,
  including extras like `article_id`).
- `annotations[]` — one entry per annotation session (skip drafts;
  `was_cancelled: true` marks skipped tasks).
- `annotations[].result[]` — one entry per answered control:
  - `from_name` — the control's name in the labeling config: `autor`, `obsah`,
    `typ_dezinformacie`, `manipulacne_techniky`, `motivacia`, `zamer`,
    `emocie`, `tema`, `narativy_<topic>` (one per topic), plus the free-text
    fields (`autor_meno_neznamy`, `autor_meno_znamy`, `neprave_tvrdenie`,
    `vyvracajuci_zdroj`);
  - `to_name` — the annotated target: `web` (snapshot mode) or `text` (text
    mode);
  - `type` — `choices` (multi-select, `value.choices` is a list),
    `choice` (single-select, `value.choice` is a scalar) or `textarea`
    (`value.text` is a list of strings);
  - `value` — the **rendered** labels as the annotator saw them (the
    translated strings from `strings.yaml`, HTML-escaped if they contain
    `&`, `<`, `>`, `"`).

## Normalizing an export

The rendered values are language-dependent strings; for analysis you want
the stable canonical keys. `build.py` emits the mapping as
`build/value_mapping.json`:

```json
{
  "sk": {
    "Anonymný autor": "choice_autor_anonymny",
    "Dezinformácia": "choice_obsah_dez"
  }
}
```

It contains **every** `choice_*` key of the language pack, independent of the
build mode. Run the normalizer:

```bash
python normalize_export.py --export export.json --mapping build/value_mapping.json -o normalized.json
```

Behavior:

- walks every task → annotation → result entry with `type` `choices` or
  `choice` (case-insensitive) and replaces each rendered value with its
  canonical key;
- the mapping is flattened across all languages first, so multi-language
  exports normalize in one pass (a flat `{value: key}` mapping is also
  accepted);
- values not present in the mapping pass through unchanged and are collected
  (deduplicated, sorted) in `unknown_values`, which is also printed as a
  stderr warning; the exit code stays 0;
- the input export file is never mutated (the export is deep-copied).

Output shape:

```json
{
  "tasks": [ /* the normalized export list */ ],
  "unknown_values": []
}
```

A single-control result before/after normalization:

```json
{"from_name": "obsah", "to_name": "web", "type": "choice",
 "value": {"choice": "Dezinformácia"}}
```

```json
{"from_name": "obsah", "to_name": "web", "type": "choice",
 "value": {"choice": "choice_obsah_dez"}}
```

`textarea` results (`value.text`) are never rewritten — only choice values
are mapped.
