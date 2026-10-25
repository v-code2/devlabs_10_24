"""DM check-in logic and escalation ladder."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.config import config
from app.db import session_scope
from app.models import Event, Task, TaskStatus, NudgeLog
from app.services import blocks as blocks_mod

log = logging.getLogger("pab.nudges")


def _in_quiet_hours(now_local: datetime) -> bool:
    """Return True if `now_local` falls inside the quiet window.

    Config quiet_hours_start >= quiet_hours_end means the window crosses midnight
    (e.g. 21..8 means 9pm → 8am). That's the normal case for us.
    """
    h = now_local.hour
    s, e = config.quiet_hours_start, config.quiet_hours_end
    if s == e:
        return False
    if s > e:
        return h >= s or h < e
    return s <= h < e


def _already_dmed_today(session, task_id: int, user_id: str, today: date) -> bool:
    row = session.scalar(
        select(NudgeLog).where(
            NudgeLog.task_id == task_id,
            NudgeLog.user_id == user_id,
            NudgeLog.day == today,
        )
    )
    return row is not None


def _record_nudge(session, task_id: int, user_id: str, today: date, kind: str) -> None:
    session.add(NudgeLog(task_id=task_id, user_id=user_id, day=today, kind=kind))


def _dm(client, user_id: str, text: str, blocks=None) -> bool:
    try:
        dm = client.conversations_open(users=user_id)
        if not dm.get("ok"):
            return False
        kwargs = {"channel": dm["channel"]["id"], "text": text}
        if blocks:
            kwargs["blocks"] = blocks
        client.chat_postMessage(**kwargs)
        return True
    except Exception as e:
        log.warning("DM to %s failed: %s", user_id, e)
        return False


def run_nudge_sweep(client) -> None:
    """Scan all events for tasks due within N days or overdue and nudge owners.

    Idempotent: one DM per (task, user, day) via NudgeLog.
    Respects quiet hours in America/Phoenix (configurable).
    """
    tz = ZoneInfo(config.timezone)
    now_local = datetime.now(tz)
    if _in_quiet_hours(now_local):
        log.info("Quiet hours (%s) — skipping nudge sweep.", now_local.isoformat())
        return

    today = now_local.date()
    lookahead = today + timedelta(days=config.nudge_lookahead_days)

    with session_scope() as s:
        tasks = s.scalars(
            select(Task).where(
                Task.status.in_([TaskStatus.todo, TaskStatus.in_progress, TaskStatus.blocked]),
                Task.due_date.isnot(None),
                Task.due_date <= lookahead,
            )
        ).all()

        for t in tasks:
            if not t.owner_user_id:
                continue
            if _already_dmed_today(s, t.id, t.owner_user_id, today):
                continue

            event = s.get(Event, t.event_id)
            if not event:
                continue

            # Pick tone from nudge_count (0=gentle, 1=firmer, >=2=final + escalate)
            tone = ["gentle", "firmer", "final"][min(t.nudge_count, 2)]
            dm_blocks = blocks_mod.nudge_dm(t, event, tone)
            text = f"Check-in: {t.title}"
            sent = _dm(client, t.owner_user_id, text, blocks=dm_blocks)
            if not sent:
                continue

            t.last_nudged_at = datetime.utcnow()
            t.nudge_count += 1
            _record_nudge(s, t.id, t.owner_user_id, today, "nudge")

            # Final nudge → escalate to director + channel
            if tone == "final":
                if event.director_user_id and event.director_user_id != t.owner_user_id:
                    if not _already_dmed_today(s, t.id, event.director_user_id, today):
                        _dm(
                            client, event.director_user_id,
                            f"🚨 *{t.title}* for *{event.name}* is overdue and <@{t.owner_user_id}> hasn't responded to prior nudges.",
                        )
                        _record_nudge(s, t.id, event.director_user_id, today, "escalation")
                try:
                    client.chat_postMessage(
                        channel=event.channel_id,
                        text=f"🚨 *{t.title}* is still open past its due date ({t.due_date.isoformat()}). Owner: <@{t.owner_user_id}>.",
                    )
                except Exception as e:
                    log.warning("escalation channel post: %s", e)


def send_pending_approvals(client) -> None:
    """DM approvers for tasks that need approval and haven't been requested yet today."""
    tz = ZoneInfo(config.timezone)
    now_local = datetime.now(tz)
    if _in_quiet_hours(now_local):
        return
    today = now_local.date()

    with session_scope() as s:
        tasks = s.scalars(
            select(Task).where(
                Task.needs_approval.is_(True),
                Task.approver_user_id.isnot(None),
                Task.status != TaskStatus.done,
            )
        ).all()
        for t in tasks:
            # Only ask approvals once per day until it's done; use NudgeLog with kind="approval".
            if _already_dmed_today(s, t.id, t.approver_user_id, today):
                continue
            # Only DM approver when the task is "ready for review" — hackathon
            # heuristic: owner has marked it in_progress AND due_date is within
            # the lookahead window.
            if t.status not in (TaskStatus.in_progress, TaskStatus.todo):
                continue
            if not t.due_date or t.due_date > today + timedelta(days=config.nudge_lookahead_days):
                continue
            event = s.get(Event, t.event_id)
            if not event:
                continue
            dm_blocks = blocks_mod.approval_dm(t, event)
            if _dm(client, t.approver_user_id, f"Approval needed: {t.title}", blocks=dm_blocks):
                t.approval_requested_at = datetime.utcnow()
                _record_nudge(s, t.id, t.approver_user_id, today, "approval")
