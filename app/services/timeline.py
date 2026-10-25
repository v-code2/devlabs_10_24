"""Build milestones backward from the event date using a YAML template."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import yaml

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "funded_campus_event.yaml"


def load_template(path: Optional[Path] = None) -> dict:
    p = path or TEMPLATE_PATH
    with open(p, "r") as f:
        return yaml.safe_load(f)


def generate_tasks_from_template(event_date: date, default_owner: Optional[str] = None) -> list[dict]:
    """Returns task dicts ready to insert as Task rows."""
    template = load_template()
    out: list[dict] = []
    for m in template.get("milestones", []):
        due = event_date - timedelta(days=int(m["days_before"]))
        out.append({
            "key": m["key"],
            "title": m["title"],
            "due_date": due,
            "needs_approval": bool(m.get("needs_approval", False)),
            "is_rff": bool(m.get("is_rff", False)),
            "owner_user_id": default_owner,
        })
    return out
