"""Event / Task / Vendor domain helpers."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Event, Task, TaskStatus, BudgetLine, Vendor, VendorStage, EventStatus,
)
from app.services.timeline import generate_tasks_from_template


def get_event_by_channel(s: Session, channel_id: str) -> Optional[Event]:
    return s.scalar(select(Event).where(Event.channel_id == channel_id))


def get_event_by_id(s: Session, event_id: int) -> Optional[Event]:
    return s.get(Event, event_id)


def create_event_with_timeline(
    s: Session,
    name: str,
    channel_id: str,
    event_date: date,
    total_budget: float,
    director_user_id: Optional[str],
) -> Event:
    event = Event(
        name=name,
        channel_id=channel_id,
        event_date=event_date,
        total_budget=total_budget,
        director_user_id=director_user_id,
        status=EventStatus.planning,
    )
    s.add(event)
    s.flush()

    tasks = generate_tasks_from_template(event_date, default_owner=director_user_id)
    for t in tasks:
        task = Task(
            event_id=event.id,
            title=t["title"],
            owner_user_id=t.get("owner_user_id"),
            due_date=t["due_date"],
            needs_approval=t["needs_approval"],
            approver_user_id=director_user_id if t["needs_approval"] else None,
        )
        if t.get("is_rff"):
            event.rff_deadline = t["due_date"]
        s.add(task)
    return event


def find_task_by_fuzzy_title(s: Session, event_id: int, needle: str) -> Optional[Task]:
    """Case-insensitive substring match. First match wins — hackathon-grade."""
    needle = needle.strip().lower()
    if not needle:
        return None
    rows = s.scalars(select(Task).where(Task.event_id == event_id)).all()
    for t in rows:
        if needle in t.title.lower():
            return t
    return None


def find_vendor_by_name(s: Session, event_id: int, name: str) -> Optional[Vendor]:
    name = name.strip().lower()
    if not name:
        return None
    rows = s.scalars(select(Vendor).where(Vendor.event_id == event_id)).all()
    for v in rows:
        if v.name.lower() == name:
            return v
    for v in rows:
        if name in v.name.lower():
            return v
    return None


def event_snapshot_dict(s: Session, event: Event) -> dict:
    """Compact serialization for grounding the LLM Q&A prompt."""
    today = date.today()
    tasks = s.scalars(select(Task).where(Task.event_id == event.id)).all()
    lines = s.scalars(select(BudgetLine).where(BudgetLine.event_id == event.id)).all()
    vendors = s.scalars(select(Vendor).where(Vendor.event_id == event.id)).all()
    return {
        "event": {
            "name": event.name,
            "date": event.event_date.isoformat(),
            "total_budget": event.total_budget,
            "rff_deadline": event.rff_deadline.isoformat() if event.rff_deadline else None,
            "director": event.director_user_id,
            "status": event.status.value,
            "today": today.isoformat(),
        },
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "owner": t.owner_user_id,
                "due": t.due_date.isoformat() if t.due_date else None,
                "status": t.status.value,
                "needs_approval": t.needs_approval,
                "approver": t.approver_user_id,
                "blocked_reason": t.blocked_reason,
            }
            for t in tasks
        ],
        "budget_lines": [
            {"label": b.label, "amount": b.amount, "state": b.state.value}
            for b in lines
        ],
        "vendors": [
            {
                "name": v.name,
                "owner": v.owner_user_id,
                "stage": v.stage.value,
                "quote_amount": v.quote_amount,
                "last_touch": v.last_touch_at.isoformat() if v.last_touch_at else None,
            }
            for v in vendors
        ],
    }
