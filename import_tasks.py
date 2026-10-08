"""Import tasks from a JSONL file into an existing Label Studio project.

Run under a venv with `label-studio` installed (Django bootstrapped the same
way as label-studio/run_import.py):

    python import_tasks.py --file tasks.jsonl --title "Project title"

Each line must be a JSON object satisfying validate_task() below. Invalid
lines are reported with their line number and skipped. If the project already
has tasks the import is skipped entirely (pass --force to append anyway), so
re-running never duplicates tasks.
"""

import argparse
import json
import os
import sys
from pathlib import Path

SNAPSHOT_FIELDS = ("snapshot_url",)
TEXT_FIELDS = ("text",)


def validate_task(obj: dict) -> list[str]:
    """Validate one task object; return a list of error strings ([] = valid).

    Valid snapshot mode: title + snapshot_url + url.
    Valid text mode: title + text + url.
    """
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["task is not a JSON object"]

    if "title" not in obj:
        errors.append("missing field 'title'")
    elif not isinstance(obj["title"], str):
        errors.append("'title' must be a string")

    if "url" not in obj:
        errors.append("missing field 'url'")
    elif not isinstance(obj["url"], str):
        errors.append("'url' must be a string")

    has_snapshot = "snapshot_url" in obj
    has_text = "text" in obj
    if has_snapshot and has_text:
        errors.append(
            "conflicting modes: use either 'snapshot_url' or 'text', not both"
        )
    elif not has_snapshot and not has_text:
        errors.append("missing field 'snapshot_url' or 'text'")
    else:
        for field in SNAPSHOT_FIELDS + TEXT_FIELDS:
            if field in obj and not isinstance(obj[field], str):
                errors.append(f"'{field}' must be a string")

    return errors


def _bootstrap_django() -> None:
    import label_studio  # type: ignore[import-not-found]

    # label-studio's settings do `from core.settings.base import *`; their
    # manage.py puts the package dir on sys.path, we do the same.
    sys.path.insert(0, str(Path(label_studio.__file__ or "").resolve().parent))

    import django  # type: ignore[import-not-found]  # noqa: E402

    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE", "label_studio.core.settings.label_studio"
    )
    django.setup()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="path to tasks.jsonl")
    parser.add_argument("--title", required=True, help="project title")
    parser.add_argument("--force", action="store_true",
                        help="append even if the project already has tasks")
    args = parser.parse_args()

    _bootstrap_django()

    from projects.models import Project  # type: ignore[import-not-found]
    from tasks.models import Task  # type: ignore[import-not-found]

    try:
        project = Project.objects.get(title=args.title)
    except Project.DoesNotExist:
        raise SystemExit(
            f"project '{args.title}' not found; run setup_project.py first"
        ) from None

    existing = project.tasks.count()
    if existing and not args.force:
        print(f"project already has {existing} tasks - import skipped")
        return

    tasks: list[dict] = []
    with open(args.file, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"line {lineno}: invalid JSON ({e}) - skipped")
                continue
            errors = validate_task(obj)
            if errors:
                print(f"line {lineno}: {'; '.join(errors)} - skipped")
                continue
            tasks.append(obj)

    Task.objects.bulk_create(Task(project=project, data=obj) for obj in tasks)
    print(
        f"imported {len(tasks)} tasks; total now: {project.tasks.count()}"
    )


if __name__ == "__main__":
    main()
