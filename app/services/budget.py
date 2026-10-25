"""Budget math helpers."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, BudgetLine, BudgetState


def totals(s: Session, event_id: int) -> dict:
    lines = s.scalars(select(BudgetLine).where(BudgetLine.event_id == event_id)).all()
    out = {"estimated": 0.0, "committed": 0.0, "spent": 0.0}
    for b in lines:
        out[b.state.value] += b.amount
    return out


def remaining(event: Event, t: dict) -> float:
    """Budget minus committed minus spent."""
    return event.total_budget - (t["committed"] + t["spent"])


def over_budget(event: Event, t: dict) -> bool:
    return (t["estimated"] + t["committed"] + t["spent"]) > event.total_budget
