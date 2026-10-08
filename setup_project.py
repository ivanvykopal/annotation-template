"""Create or update the Label Studio project from build/ artifacts.

Run under a venv with `label-studio` installed (Django is bootstrapped the
same way as label-studio/run_import.py):

    python setup_project.py --email you@example.org --title "Project title"

Idempotent: re-running updates the config/guidelines of the existing project,
it never duplicates projects.
"""

import argparse
import os
import sys
from pathlib import Path

import label_studio  # type: ignore[import-not-found]  # resolved in repo venv

# label-studio's settings do `from core.settings.base import *`; their
# manage.py puts the package dir on sys.path, we do the same.
sys.path.insert(0, str(Path(label_studio.__file__ or "").resolve().parent))

import django  # type: ignore[import-not-found]  # noqa: E402

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "label_studio.core.settings.label_studio"
)
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from projects.models import Project  # type: ignore[import-not-found]  # noqa: E402

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "build" / "labeling_config.xml"
GUIDELINES_PATH = BASE / "build" / "guidelines.html"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=None,
                        help="owner's email (default: first user)")
    parser.add_argument("--title", required=True, help="project title")
    args = parser.parse_args()

    try:
        config = CONFIG_PATH.read_text(encoding="utf-8")
        guidelines = GUIDELINES_PATH.read_text(encoding="utf-8")
    except OSError as e:
        raise SystemExit(
            f"missing build artifact: {e} "
            "(run `python build.py --language <code>` first)"
        ) from e

    User = get_user_model()
    if args.email:
        user = User.objects.get(email=args.email)
    else:
        user = User.objects.first()
        if user is None:
            raise SystemExit("no users exist; pass --email after creating one")

    project, created = Project.objects.get_or_create(
        title=args.title,
        defaults={"created_by": user, "organization": user.organizations.first()},
    )
    print("created:", created, "| project id:", project.id)
    project.label_config = config
    project.validate_label_config(config)
    project.expert_instruction = guidelines
    project.show_instruction = True
    project.save()
    print("config valid, tasks:", project.tasks.count())


if __name__ == "__main__":
    main()
