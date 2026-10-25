"""@app_mention Q&A in event channels and message.im plain-language updates."""
from __future__ import annotations

import logging
import re

from sqlalchemy import select

from app.db import session_scope
from app.models import Event, Task
from app.services.events import get_event_by_channel, event_snapshot_dict
from app.services.llm import answer_question, parse_update
from app.services.llm_apply import store_pending, build_pending_summary
from app.services import blocks as blocks_mod

log = logging.getLogger("pab.mentions")

_MENTION_RE = re.compile(r"<@[UW][A-Z0-9]+(?:\|[^>]+)?>")


def _strip_mentions(text: str) -> str:
    return _MENTION_RE.sub("", text or "").strip()


def register(app) -> None:

    @app.event("app_mention")
    def on_app_mention(event, client):
        channel_id = event["channel"]
        user = event.get("user")
        text = _strip_mentions(event.get("text", ""))
        if not text:
            client.chat_postMessage(channel=channel_id, text=f"<@{user}> ask me something about this event.")
            return

        with session_scope() as s:
            ev = get_event_by_channel(s, channel_id)
            if not ev:
                client.chat_postMessage(
                    channel=channel_id,
                    text="I don't have an event for this channel yet. Use `/newevent` to create one.",
                )
                return
            snapshot = event_snapshot_dict(s, ev)

        try:
            reply = answer_question(text, snapshot)
        except Exception as e:
            log.exception("answer_question failed")
            reply = f"Sorry — I couldn't answer that right now ({e})."

        client.chat_postMessage(
            channel=channel_id,
            text=reply,
            thread_ts=event.get("thread_ts") or event.get("ts"),
        )

    @app.event("message")
    def on_dm_message(event, client, logger):
        """DMs: parse plain-language updates, DM back a confirmation."""
        # Only handle plain IMs from humans, not bot echoes, edits, or threaded joins.
        if event.get("channel_type") != "im":
            return
        if event.get("subtype"):
            return
        if event.get("bot_id") or event.get("user") is None:
            return

        user_id = event["user"]
        text = (event.get("text") or "").strip()
        if not text:
            return

        # Scope: use the single most-recent event where this user owns a task
        # OR directs. Hackathon-grade: good enough for a demo. A real version
        # would ask which event.
        with session_scope() as s:
            event_row = _find_user_event(s, user_id)
            if not event_row:
                client.chat_postMessage(
                    channel=event["channel"],
                    text="Thanks — but I don't know which event this is about. Mention me in an event channel instead.",
                )
                return
            snapshot = event_snapshot_dict(s, event_row)
            event_id = event_row.id

        parsed = parse_update(text, snapshot)
        if parsed.get("_error") and not any(k in parsed for k in ("task_update", "vendor_update", "budget_line")):
            client.chat_postMessage(
                channel=event["channel"],
                text=f"I couldn't parse that: {parsed['_error']}. Try phrasing it like 'got a quote from Pizza Co for $450'.",
            )
            return

        pending_id = store_pending(event_id, user_id, text, parsed, channel_id=event["channel"])
        summary_lines = build_pending_summary(parsed)
        client.chat_postMessage(
            channel=event["channel"],
            text="Confirm this update?",
            blocks=blocks_mod.pending_update_blocks(pending_id, text, summary_lines),
        )


def _find_user_event(s, user_id: str):
    """Pick the most-recent event the user owns a task in, else they direct."""
    row = s.scalar(
        select(Event)
        .join(Task, Task.event_id == Event.id)
        .where(Task.owner_user_id == user_id)
        .order_by(Event.created_at.desc())
    )
    if row:
        return row
    return s.scalar(
        select(Event).where(Event.director_user_id == user_id).order_by(Event.created_at.desc())
    )
