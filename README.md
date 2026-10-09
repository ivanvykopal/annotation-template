# Annotation Template

Label Studio annotation setup for the Slavic NLP 2027 disinformation corpus.
A language pack (`languages/<lang>/`) plus a shared `config.template.xml` are
rendered into a Label Studio labeling config; tasks are imported from JSONL,
article snapshots are served by a small CORS server, and finished exports are
normalized back to canonical taxonomy keys.

## Repository layout

| Path | Purpose |
|---|---|
| `config.template.xml` | Shared labeling-config template with `{{key}}` placeholders and `{{#MODE}}` blocks |
| `languages/en/` | English language pack (from the original English guideline documents) |
| `languages/sk/` | Slovak language pack: `strings.yaml` (all `{{key}}` values) + `guidelines.html` (annotator instructions) |
| `build.py` | Render the template → `build/labeling_config.xml`, `build/guidelines.html`, `build/value_mapping.json` |
| `setup_project.py` | Create/update the Label Studio project from `build/` artifacts (needs `label-studio` installed) |
| `import_tasks.py` | Import `tasks.jsonl` into the project (needs `label-studio` installed) |
| `cors_server.py` | Serve `snapshots/` on `127.0.0.1:8765` with CORS for the annotation UI |
| `start.sh` / `start.bat` | Start the stack: CORS server + Label Studio |
| `export_to_csv.py` | Convert a JSON export to the final dataset CSV (`label`, `language`, article columns) |
| `tasks.example.snapshot.jsonl` / `tasks.example.text.jsonl` | Example task file per mode (snapshot and text; one mode per file — never mix) |
| `snapshots/EXAMPLE.html` | Example served article snapshot |
| `tools/` | Snapshot pipeline: raw article HTML → sanitized, self-contained snapshots (see [docs/SNAPSHOT_PIPELINE.md](docs/SNAPSHOT_PIPELINE.md)) |
| `tests/` | Pytest suite for build/import-validation/normalize |

Data formats (task JSONL schemas, export walkthrough) are documented in
[docs/DATA.md](docs/DATA.md).

## Try the included example (5 minutes)

This reproduces two demo projects — one per task mode — using the shipped
example files. Run from this directory with the venv from step 1 activated.

```bash
# snapshot mode: article rendered as embedded HTML
python build.py --language sk
python setup_project.py --title "Annotation Template Demo"
python import_tasks.py --file tasks.example.snapshot.jsonl --title "Annotation Template Demo"

# text mode: article body as plain text (separate build AND separate project)
python build.py --language sk --text
python setup_project.py --title "Annotation Template Demo (text)"
python import_tasks.py --file tasks.example.text.jsonl --title "Annotation Template Demo (text)"

# rebuild the default (snapshot) config so build/ matches the first project
python build.py --language sk
```

Then start the stack (step 6 below), open <http://localhost:8080>, and click
through the one task in each project. Delete the two demo projects in the UI
when done. The same steps with your own `tasks.jsonl` and `--language <code>`
are the real workflow.

## Quickstart

Requirements: Python 3.10+ (verified with 3.13). All commands below are run
from this directory. Lines starting `#` are Linux/macOS (`start.sh`-flavored)
alternatives.

### 1. Create a venv and install dependencies

```bash
python -m venv venv
venv\Scripts\activate            # Linux/macOS: source venv/bin/activate
pip install label-studio pyyaml requests
```

`label-studio` is only needed for `setup_project.py`, `import_tasks.py` and
the `label-studio` server itself; `pyyaml` for `build.py`; `requests` for
`tools/`. Any Python that already has `label-studio` installed works for the
Django-dependent scripts — the start scripts assume the venv lives in
`venv/` next to this file.

### 2. Build the labeling config

```bash
python build.py --language sk
```

Writes `build/labeling_config.xml`, `build/guidelines.html` and
`build/value_mapping.json` (mode-independent superset of all choice keys,
keyed by the raw unescaped label text Label Studio exports). Both the config
and the guidelines are mode-aware: sections of `guidelines.html` wrapped in
`{{#FULL}}`…`{{/FULL}}` (the fine-grained Steps II–IV instructions) are
stripped in `binary` mode so annotators never see instructions for
questions their form does not contain.
Flags: `--mode binary|full` (default `binary`), `--text` (text mode, no
snapshot embed). See *Modes* below.

### 3. Create the Label Studio project

```bash
python setup_project.py --title "Hodnotenie článkov – dezinformácie"
```

`--email` is optional (defaults to the first user in the database).
Idempotent: re-running after a rebuild updates the config/guidelines of the
existing project; it never duplicates projects.

### 4. Prepare tasks

Create `tasks.jsonl` — one flat JSON object per line, either snapshot mode
(`title` + `url` + `snapshot_url`) or text mode (`title` + `url` + `text`).
Exact schemas and rules: [docs/DATA.md](docs/DATA.md). Ready-made examples:
`tasks.example.snapshot.jsonl` (snapshot mode) and
`tasks.example.text.jsonl` (text mode) — a file must contain ONE mode only,
because the labeling config is built for a single mode; `import_tasks.py`
rejects mixed files. Snapshot-mode files must exist under `snapshots/`
and be referenced as `http://127.0.0.1:8765/<file>.html` (see
[docs/SNAPSHOT_PIPELINE.md](docs/SNAPSHOT_PIPELINE.md) for producing them from
raw article HTML).

### 5. Import the tasks

```bash
python import_tasks.py --file tasks.jsonl --title "Hodnotenie článkov – dezinformácie"
```

Invalid lines are reported with their line number and skipped. If the project
already has tasks the import is skipped entirely; pass `--force` to append
anyway.

### 6. Start the annotation stack

```bash
start.bat    # Linux/macOS: ./start.sh
```

This starts the snapshot CORS server on `127.0.0.1:8765` in a background
window and Label Studio on `127.0.0.1:8080` in the foreground. Or start the
two pieces manually:

```bash
python cors_server.py          # serves snapshots/ on 127.0.0.1:8765
label-studio                  # or: venv/bin/label-studio
```

### 7. Annotate

Open <http://localhost:8080>, log in with your Label Studio account, open the
project and annotate. Article snapshots are embedded in the task view; the
questionnaire unfolds step by step depending on the answers. The full
annotator instructions are shown via the *Instructions* button (they come
from `languages/<lang>/guidelines.html`).

### 8. Export the annotations

In the Label Studio UI: open the project → *Export* → choose **JSON**. This
produces a list of task objects whose annotation results contain the rendered
(human-readable) choice values.

### 9. Normalize the export

```bash
python normalize_export.py --export export.json --mapping build/value_mapping.json -o normalized.json
```

Replaces every choice value with its canonical YAML key (`choice_*`);
unrecognized values pass through unchanged and are reported on stderr and in
the output's `unknown_values` list. Details: [docs/DATA.md](docs/DATA.md).

### 10. Convert the export to the final CSV

```bash
python export_to_csv.py export.json --language sk -o annotations.csv
```

Writes the dataset CSV with the columns `article_id`,
`article_publication_date`, `article_title`, `article_url`, `article_body`,
`content` (title + blank line + body), `label` (`credible`/`disinfo`), and
`language`. Labels are resolved through `build/value_mapping.json`, so this
works for any language pack; undecided tasks (hard-to-say / off-topic) are
skipped with a summary on stderr. The optional task data fields `article_id`,
`published`, and `language` feed the CSV columns (see
[docs/DATA.md](docs/DATA.md)).

## Adapting to another language

1. Copy the language pack: `cp -r languages/sk languages/<code>`
   (e.g. `languages/cs`).
2. Translate `languages/<code>/strings.yaml`. Every key must stay — the build
   fails with `error: missing keys: ...` if a `{{key}}` in the template has no
   entry. `{{target}}` is not a key in this file (see *Modes*).
3. Translate `languages/<code>/guidelines.html` (plain HTML, shown to
   annotators).
4. Build and create the project with `--language <code>`.

Two packs ship as references: `sk` (the original Slovak) and `en` (from the
original English guideline documents) — copy whichever is closer to your
target language.

## value_mapping.json across languages

`build/value_mapping.json` is keyed by language
(`{"<lang>": {rendered_value: canonical_key}}`). Each build merges its
language's mapping into the existing file, so building several languages
accumulates a combined mapping; `normalize_export.py` flattens all
languages present into one lookup, so a single normalizer run handles
exports from any built language's project.

## Adapting the taxonomy

All choice labels live in `languages/<lang>/strings.yaml` under
`choice_*` keys (plus their `hint_*` tooltips where present). The XML in
`config.template.xml` references them as `{{choice_*}}`.

- **Add or remove a simple choice** (author type, disinformation type,
  manipulation technique, motivation, intention, emotion): edit the
  `choice_*`/`hint_*` keys in `strings.yaml` **and** the matching
  `<Choice value="{{choice_*}}"/>` line in `config.template.xml`.
- **Add or remove a topic or narrative**: this touches two places in the
  template — the topic list in question 3.4 (`<Choices name="tema">`) and the
  topic's narrative block in step 4
  (`<View visibleWhen="choice-selected" whenTagName="tema"
  whenChoiceValue="{{choice_tema_*}}">` containing
  `<Choices name="narativy_<topic>">`). Removing a topic/narrative requires
  editing **both** the template block and the YAML keys; a `{{key}}` left in
  the template without a YAML entry breaks the build (unused YAML keys are
  harmless but should be removed for hygiene).
- Re-run `python build.py --language sk` afterwards — it fails loudly on
  missing keys or invalid XML, and regenerates `value_mapping.json` so
  exports keep normalizing to canonical keys.

## Modes

Two orthogonal dimensions, chosen at build time:

- `--mode binary|full` — **binary** (default): selecting *Dezinformácia* in
  question 1.2 ends the annotation (only author + content rating).
  **full**: the disinformation path continues to step 2 (type of
  disinformation), step 3 (motivation, intention, emotions, topic) and step 4
  (narratives of the chosen topic).
- `--text` — build for text-mode tasks (`$text` body, `<Text name="text">`).
  Default (no flag) is snapshot mode: the article is embedded via
  `<HyperText name="web" value="$snapshot_url" valueType="url">`. `{{target}}`
  in the template resolves to `text` or `web` accordingly.

The mode must match the tasks: a snapshot-mode config cannot display `text`
tasks and vice versa. `value_mapping.json` always contains the superset of
all `choice_*` keys, independent of mode.

## CLI reference

| Script | Flags |
|---|---|
| `build.py` | `--language <code>` (required), `--mode binary\|full` (default `binary`), `--text` |
| `setup_project.py` | `--title` (required), `--email` (optional, defaults to first user) |
| `import_tasks.py` | `--file <tasks.jsonl>` (required), `--title` (required), `--force` (append even if the project has tasks) |
| `cors_server.py` | `--root DIR` (default `snapshots/`), `--port PORT` (default `8765`) |
| `export_to_csv.py` | `export.json` (positional, required), `--mapping <file>` (default `build/value_mapping.json`), `--language <tag>` (e.g. `pl`, overridable per task via a `language` data field), `-o/--out <file>` (default `annotations.csv`) |

## Troubleshooting

- **`error: missing keys: ...` (build.py)** — the template references a
  `{{key}}` that `languages/<lang>/strings.yaml` does not define. Add the key
  (or remove the template reference).
- **`[Errno 2] No such file or directory: ...strings.yaml` (build.py)** —
  unknown language code: `languages/<code>/` does not exist.
- **`error: rendered XML does not parse: ...` (build.py)** — the template was
  edited into invalid XML (or a string contains raw `<`/`&`; escape them in
  `strings.yaml`).
- **`missing build artifact: ... (run 'python build.py --language <code>' first)` (setup_project.py)** — run `build.py` before `setup_project.py`.
- **Config validation errors (setup_project.py)** — the rendered config
  violates Label Studio's tag schema; usually caused by hand-editing
  `config.template.xml`. Check the `<Choices>`/`<Choice>` structure and the
  `toName` targets.
- **`no users exist; pass --email after creating one` (setup_project.py)** —
  create a Label Studio user first (log in once to the web UI), or point
  `--email` at an existing account.
- **`project '<title>' not found; run setup_project.py first` (import_tasks.py)** — create the project before importing.
- **`project already has N tasks - import skipped` (import_tasks.py)** —
  expected on re-run; pass `--force` to append, or import into a fresh
  project.
- **Snapshots not loading in the annotation UI** (blank article panel /
  `TypeError: Failed to fetch`) — the CORS server is not running, or the
  snapshot file is not under the served directory. Start it
  (`python cors_server.py`, or use `start.bat`/`start.sh`) and check that the
  task's `snapshot_url` (default `http://127.0.0.1:8765/<file>.html`) matches
  a file inside `snapshots/`. Note the server only sends CORS headers for
  Label Studio origins on ports 8080/8081 — running Label Studio on another
  port will also break snapshot embedding.
- **`warning: N unknown value(s) passed through` (normalize_export.py)** — the
  export contains choice values that are not in `value_mapping.json`; usually
  a taxonomy change between build and export. The values are kept unchanged
  and listed in the output's `unknown_values`.

## Further docs

- [docs/DATA.md](docs/DATA.md) — task JSONL schemas, export format walkthrough, value normalization
- [docs/SNAPSHOT_PIPELINE.md](docs/SNAPSHOT_PIPELINE.md) — turning raw article HTML into served snapshots
