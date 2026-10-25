"""Monday 9am weekly digest, per event channel."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.config import config
from app.db import session_scope
from app.models import Event, Task, TaskStatus, Vendor, BudgetLine, BudgetState

log = logging.getLogger("pab.digest")


def _build_digest_blocks(event: Event, tasks: list[Task], vendors: list[Vendor], lines: list[BudgetLine], today: date) -> list[dict]:
    done = [t for t in tasks if t.status == TaskStatus.done]
    overdue = [t for t in tasks if t.status != TaskStatus.done and t.due_date and t.due_date < today]
    upcoming = [
        t for t in tasks
        if t.status != TaskStatus.done and t.due_date and today <= t.due_date <= today + timedelta(days=7)
    ]

    totals = {"estimated": 0.0, "committed": 0.0, "spent": 0.0}
    for b in lines:
        totals[b.state.value] += b.amount
    remaining = event.total_budget - (totals["committed"] + totals["spent"])

    stalled = []
    cutoff = datetime.utcnow() - timedelta(days=config.stalled_vendor_days)
    for v in vendors:
        if v.stage.value in ("chosen",):
            continue
        if (v.last_touch_at or datetime(1970, 1, 1)) < cutoff:
            stalled.append(v)

    def fmt_task(t: Task) -> str:
        owner = f"<@{t.owner_user_id}>" if t.owner_user_id else "_unassigned_"
        due = t.due_date.isoformat() if t.due_date else "—"
        return f"• `{due}`  {t.title} — {owner}"

    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Weekly digest — {event.name}"[:150]}},
        {"type": "section", "text": {"type": "mrkdwn", "text":
            f"*Event date:* {event.event_date.isoformat()}  •  "
            f"*Budget:* ${event.total_budget:,.0f}  •  "
            f"*Remaining:* ${remaining:,.0f}"}},
    ]
    if overdue:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": "*⚠️ Overdue*\n" + "\n".join(fmt_task(t) for t in overdue)}})
    if upcoming:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": "*Upcoming 7 days*\n" + "\n".join(fmt_task(t) for t in sorted(upcoming, key=lambda x: x.due_date))}})
    if done:
        recent_done = sorted(done, key=lambda t: t.id)[-5:]
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": "*✅ Recently done*\n" + "\n".join(f"• {t.title}" for t in recent_done)}})
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
        "text": "*Budget snapshot*\n"
                f"Estimated: ${totals['estimated']:,.0f} • "
                f"Committed: ${totals['committed']:,.0f} • "
                f"Spent: ${totals['spent']:,.0f}"}})
    if stalled:
        rows = []
        for v in stalled:
            last = v.last_touch_at.date().isoformat() if v.last_touch_at else "never"
            owner = f"<@{v.owner_user_id}>" if v.owner_user_id else "_unassigned_"
            rows.append(f"• {v.name} ({v.stage.value}) — last touch *{last}* — {owner}")
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*Vendors stalled >{config.stalled_vendor_days}d*\n" + "\n".join(rows)}})
    return blocks


def post_weekly_digest(slack_client) -> None:
    tz = ZoneInfo(config.timezone)
    today = datetime.now(tz).date()
    with session_scope() as s:
        events = s.scalars(select(Event).where(Event.status != None)).all()
        for ev in events:
            if ev.event_date < today - timedelta(days=7):
                # Event is well past — skip.
                continue
            tasks = s.scalars(select(Task).where(Task.event_id == ev.id)).all()
            vendors = s.scalars(select(Vendor).where(Vendor.event_id == ev.id)).all()
            lines = s.scalars(select(BudgetLine).where(BudgetLine.event_id == ev.id)).all()
            blocks = _build_digest_blocks(ev, list(tasks), list(vendors), list(lines), today)
            try:
                slack_client.chat_postMessage(
                    channel=ev.channel_id, blocks=blocks,
                    text=f"Weekly digest for {ev.name}",
                )
            except Exception as e:
                log.warning("digest post to %s failed: %s", ev.channel_id, e)
