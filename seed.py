"""Seed the DB with a demo Homecoming Mixer event for a hackathon demo."""
from datetime import date, timedelta, datetime

from app.db import init_db, session_scope
from app.models import (
    Event, Task, BudgetLine, Vendor,
    EventStatus, TaskStatus, BudgetState, VendorStage,
)
from app.services.timeline import generate_tasks_from_template


DEMO_CHANNEL_ID = "C_DEMO_HOMECOMING"
DEMO_DIRECTOR = "U_DEMO_DIRECTOR"
DEMO_OWNER_A = "U_DEMO_OWNER_A"
DEMO_OWNER_B = "U_DEMO_OWNER_B"


def run() -> None:
    init_db()
    with session_scope() as s:
        existing = s.query(Event).filter_by(channel_id=DEMO_CHANNEL_ID).first()
        if existing:
            print(f"Demo event already exists: id={existing.id}")
            return

        event_date = date.today() + timedelta(weeks=6)
        event = Event(
            name="Homecoming Mixer",
            channel_id=DEMO_CHANNEL_ID,
            event_date=event_date,
            total_budget=2000.0,
            director_user_id=DEMO_DIRECTOR,
            status=EventStatus.planning,
        )
        s.add(event)
        s.flush()

        tasks = generate_tasks_from_template(event_date, default_owner=DEMO_OWNER_A)
        # Assign a second owner to the vendor outreach task for variety
        for t in tasks:
            e_task = Task(
                event_id=event.id,
                title=t["title"],
                owner_user_id=DEMO_OWNER_B if "vendor" in t["title"].lower() else DEMO_OWNER_A,
                due_date=t["due_date"],
                needs_approval=t.get("needs_approval", False),
                approver_user_id=DEMO_DIRECTOR if t.get("needs_approval") else None,
            )
            if t.get("is_rff"):
                event.rff_deadline = t["due_date"]
            s.add(e_task)

        s.add_all([
            BudgetLine(event_id=event.id, label="DJ (estimated)", amount=400.0, state=BudgetState.estimated),
            BudgetLine(event_id=event.id, label="Catering (estimated)", amount=600.0, state=BudgetState.estimated),
            BudgetLine(event_id=event.id, label="Decor", amount=150.0, state=BudgetState.committed),
        ])

        s.add_all([
            Vendor(
                event_id=event.id, name="Pizza Co", owner_user_id=DEMO_OWNER_A,
                stage=VendorStage.contacted, last_touch_at=datetime.utcnow() - timedelta(days=6),
            ),
            Vendor(
                event_id=event.id, name="DJ Marco", owner_user_id=DEMO_OWNER_B,
                stage=VendorStage.not_contacted,
            ),
        ])

        print(f"Seeded event '{event.name}' id={event.id} on {event_date}")


if __name__ == "__main__":
    run()
