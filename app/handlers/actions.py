"""Button / modal submission handlers."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime

from sqlalchemy import select

from app.db import session_scope
from app.models import Event, Task, TaskStatus, PendingUpdate
from app.services import blocks as blocks_mod
from app.services.events import create_event_with_timeline, get_event_by_id

log = logging.getLogger("pab.actions")


def _dm_user(client, user_id: str, text: str, blocks=None) -> None:
    try:
        dm = client.conversations_open(users=user_id)
        if dm.get("ok"):
            kwargs = {"channel": dm["channel"]["id"], "text": text}
            if blocks:
                kwargs["blocks"] = blocks
            client.chat_postMessage(**kwargs)
    except Exception as e:
        log.warning("DM to %s failed: %s", user_id, e)


def register(app) -> None:

    # ---------- New event modal submission ----------
    @app.view("new_event_submit")
    def submit_new_event(ack, body, view, client):
        try:
            values = view["state"]["values"]
            name = values["name"]["val"]["value"].strip()
            event_date = date.fromisoformat(values["event_date"]["val"]["selected_date"])
            budget_str = values["budget"]["val"]["value"]
            total_budget = float(budget_str)
            channel_id = values["channel"]["val"]["selected_channel"]
        except Exception as e:
            ack({"response_action": "errors", "errors": {"name": f"Invalid input: {e}"}})
            return

        director = body["user"]["id"]
        ack()

        with session_scope() as s:
            existing = s.scalar(select(Event).where(Event.channel_id == channel_id))
            if existing:
                _dm_user(client, director, f"There's already an event in <#{channel_id}>: *{existing.name}*. Delete it first or use a different channel.")
                return
            event = create_event_with_timeline(
                s=s, name=name, channel_id=channel_id,
                event_date=event_date, total_budget=total_budget,
                director_user_id=director,
            )
            s.flush()
            tasks = s.scalars(select(Task).where(Task.event_id == event.id)).all()
            summary_blocks = blocks_mod.event_summary(event, list(tasks))
            event_name = event.name

        # Invite the bot into the channel if needed, then post + pin the summary.
        try:
            client.conversations_join(channel=channel_id)
        except Exception as e:
            log.debug("conversations_join: %s", e)

        try:
            posted = client.chat_postMessage(
                channel=channel_id, blocks=summary_blocks, text=f"Timeline for {event_name}",
            )
            if posted.get("ok"):
                try:
                    client.pins_add(channel=channel_id, timestamp=posted["ts"])
                except Exception as e:
                    log.warning("pins_add: %s", e)
        except Exception as e:
            log.exception("Failed to post event summary")
            _dm_user(client, director, f"Created the event, but couldn't post to <#{channel_id}>: {e}")

    # ---------- Nudge buttons ----------
    @app.action("nudge_done")
    def nudge_done(ack, body, client):
        ack()
        task_id = int(body["actions"][0]["value"])
        _apply_task_status(client, body, task_id, TaskStatus.done, "Marked as done — nice work. ✅")

    @app.action("nudge_in_progress")
    def nudge_in_progress(ack, body, client):
        ack()
        task_id = int(body["actions"][0]["value"])
        _apply_task_status(client, body, task_id, TaskStatus.in_progress, "Got it — marked in progress.")

    @app.action("nudge_blocked")
    def nudge_blocked(ack, body, client):
        ack()
        task_id = int(body["actions"][0]["value"])
        channel = body.get("channel", {}).get("id")
        try:
            client.views_open(
                trigger_id=body["trigger_id"],
                view=blocks_mod.blocked_reason_modal(task_id, channel),
            )
        except Exception as e:
            log.exception("Could not open blocked reason modal: %s", e)

    @app.view("blocked_reason_submit")
    def blocked_reason_submit(ack, body, view, client):
        ack()
        meta = view.get("private_metadata", "")
        task_id_str, _, _ = meta.partition("|")
        try:
            task_id = int(task_id_str)
        except ValueError:
            return
        reason = view["state"]["values"]["reason"]["val"]["value"].strip()
        user_id = body["user"]["id"]

        with session_scope() as s:
            task = s.get(Task, task_id)
            if not task:
                return
            task.status = TaskStatus.blocked
            task.blocked_reason = reason
            event = s.get(Event, task.event_id)
            event_channel = event.channel_id if event else None
            event_name = event.name if event else "the event"
            director = event.director_user_id if event else None
            task_title = task.title

        if director and director != user_id:
            _dm_user(client, director,
                     f"<@{user_id}> is blocked on *{task_title}* for *{event_name}*:\n> {reason}")
        if event_channel:
            try:
                client.chat_postMessage(
                    channel=event_channel,
                    text=f"🚧 <@{user_id}> flagged *{task_title}* as blocked: {reason}",
                )
            except Exception as e:
                log.warning("post blocked note: %s", e)

    # ---------- Approval buttons ----------
    @app.action("approval_approve")
    def approval_approve(ack, body, client):
        ack()
        task_id = int(body["actions"][0]["value"])
        approver = body["user"]["id"]
        with session_scope() as s:
            task = s.get(Task, task_id)
            if not task:
                return
            task.status = TaskStatus.done
            event = s.get(Event, task.event_id)
            owner = task.owner_user_id
            event_name = event.name if event else "the event"
            event_channel = event.channel_id if event else None
            task_title = task.title
        if owner:
            _dm_user(client, owner, f"✅ <@{approver}> approved *{task_title}* for *{event_name}*.")
        if event_channel:
            try:
                client.chat_postMessage(
                    channel=event_channel,
                    text=f"✅ *{task_title}* approved by <@{approver}>.",
                )
            except Exception as e:
                log.warning("post approval: %s", e)

    @app.action("approval_changes")
    def approval_changes(ack, body, client):
        ack()
        task_id = int(body["actions"][0]["value"])
        try:
            client.views_open(
                trigger_id=body["trigger_id"],
                view=blocks_mod.changes_requested_modal(task_id),
            )
        except Exception as e:
            log.exception("could not open changes modal: %s", e)

    @app.view("changes_requested_submit")
    def changes_requested_submit(ack, body, view, client):
        ack()
        try:
            task_id = int(view["private_metadata"])
        except ValueError:
            return
        feedback = view["state"]["values"]["feedback"]["val"]["value"].strip()
        approver = body["user"]["id"]
        with session_scope() as s:
            task = s.get(Task, task_id)
            if not task:
                return
            task.status = TaskStatus.in_progress
            event = s.get(Event, task.event_id)
            owner = task.owner_user_id
            event_name = event.name if event else "the event"
            task_title = task.title
        if owner:
            _dm_user(
                client, owner,
                f"<@{approver}> requested changes on *{task_title}* for *{event_name}*:\n> {feedback}",
            )

    # ---------- Pending LLM update confirmation ----------
    @app.action("pending_confirm")
    def pending_confirm(ack, body, client):
        ack()
        pending_id = int(body["actions"][0]["value"])
        from app.services.llm_apply import apply_pending_update
        summary = apply_pending_update(pending_id)
        try:
            client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text="Applied.",
                blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "✅ Applied:\n" + summary}}],
            )
        except Exception as e:
            log.warning("chat_update after confirm: %s", e)

    @app.action("pending_edit")
    def pending_edit(ack, body, client):
        ack()
        pending_id = int(body["actions"][0]["value"])
        try:
            client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text="Edit by replying.",
                blocks=[{"type": "section", "text": {"type": "mrkdwn",
                        "text": f"OK — reply with the corrected sentence and I'll re-parse (pending #{pending_id})."}}],
            )
        except Exception as e:
            log.warning("chat_update after edit: %s", e)
        _discard_pending(pending_id)

    @app.action("pending_discard")
    def pending_discard(ack, body, client):
        ack()
        pending_id = int(body["actions"][0]["value"])
        _discard_pending(pending_id)
        try:
            client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text="Discarded.",
                blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "🗑 Discarded."}}],
            )
        except Exception as e:
            log.warning("chat_update after discard: %s", e)


def _apply_task_status(client, body, task_id: int, status: TaskStatus, confirm_text: str) -> None:
    with session_scope() as s:
        task = s.get(Task, task_id)
        if not task:
            return
        task.status = status
    try:
        client.chat_update(
            channel=body["channel"]["id"],
            ts=body["message"]["ts"],
            text=confirm_text,
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": confirm_text}}],
        )
    except Exception as e:
        log.warning("chat_update: %s", e)


def _discard_pending(pending_id: int) -> None:
    with session_scope() as s:
        p = s.get(PendingUpdate, pending_id)
        if p:
            s.delete(p)
