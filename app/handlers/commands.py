"""All slash command handlers."""
from __future__ import annotations

import logging
import shlex
from datetime import date, datetime

from sqlalchemy import select

from app.db import session_scope
from app.models import Event, Task, Vendor, VendorStage
from app.services import blocks as blocks_mod
from app.services.events import (
    get_event_by_channel, create_event_with_timeline, find_task_by_fuzzy_title,
    find_vendor_by_name,
)

log = logging.getLogger("pab.commands")


def _friendly_error(respond, msg: str) -> None:
    respond({"response_type": "ephemeral", "text": msg})


def register(app) -> None:

    # /ping is defined in main for the smoke test; we keep it there.

    @app.command("/newevent")
    def new_event(ack, body, client, respond):
        ack()
        try:
            client.views_open(
                trigger_id=body["trigger_id"],
                view=blocks_mod.new_event_modal(),
            )
        except Exception as e:
            log.exception("views_open failed")
            _friendly_error(respond, f"Couldn't open the New Event dialog: {e}")

    @app.command("/status")
    def status(ack, respond, command, client):
        ack()
        channel_id = command["channel_id"]
        with session_scope() as s:
            event = get_event_by_channel(s, channel_id)
            if not event:
                _friendly_error(respond, "No event found for this channel. Use `/newevent` first.")
                return
            tasks = s.scalars(select(Task).where(Task.event_id == event.id)).all()
            blocks = blocks_mod.status_blocks(event, list(tasks), date.today())
        respond({"response_type": "in_channel", "blocks": blocks, "text": f"Status for {event.name}"})

    @app.command("/budget")
    def budget(ack, respond, command):
        ack()
        channel_id = command["channel_id"]
        from app.models import BudgetLine
        with session_scope() as s:
            event = get_event_by_channel(s, channel_id)
            if not event:
                _friendly_error(respond, "No event found for this channel. Use `/newevent` first.")
                return
            lines = s.scalars(select(BudgetLine).where(BudgetLine.event_id == event.id)).all()
            blocks = blocks_mod.budget_blocks(event, list(lines))
        respond({"response_type": "in_channel", "blocks": blocks, "text": f"Budget for {event.name}"})

    @app.command("/assign")
    def assign(ack, respond, command, client):
        """Usage: /assign <task fuzzy title> @user"""
        ack()
        text = (command.get("text") or "").strip()
        if not text:
            _friendly_error(respond, "Usage: `/assign <task name> @user`")
            return

        # Pull trailing user mention (<@UXXXX>) off the end.
        import re
        m = re.search(r"<@([UW][A-Z0-9]+)(\|[^>]+)?>\s*$", text)
        if not m:
            _friendly_error(respond, "I need an @user at the end — e.g. `/assign DJ outreach @alex`")
            return
        user_id = m.group(1)
        task_needle = text[: m.start()].strip()
        if not task_needle:
            _friendly_error(respond, "Which task? e.g. `/assign DJ outreach @alex`")
            return

        channel_id = command["channel_id"]
        with session_scope() as s:
            event = get_event_by_channel(s, channel_id)
            if not event:
                _friendly_error(respond, "No event in this channel. Use `/newevent` first.")
                return
            task = find_task_by_fuzzy_title(s, event.id, task_needle)
            if not task:
                _friendly_error(respond, f"No task matched `{task_needle}`.")
                return
            task.owner_user_id = user_id
            s.flush()
            event_name = event.name
            task_title = task.title
            task_due = task.due_date

        try:
            dm = client.conversations_open(users=user_id)
            if dm.get("ok"):
                due = task_due.isoformat() if task_due else "—"
                client.chat_postMessage(
                    channel=dm["channel"]["id"],
                    text=f"You've been assigned *{task_title}* for *{event_name}* (due {due}).",
                )
        except Exception as e:
            log.warning("DM to %s failed: %s", user_id, e)

        respond({"response_type": "in_channel",
                 "text": f"Assigned *{task_title}* to <@{user_id}>."})

    @app.command("/vendor")
    def vendor(ack, respond, command):
        """
        /vendor add <name> [@owner]
        /vendor update <name> stage=<stage> [quote=<amount>]
        /vendor list
        """
        ack()
        text = (command.get("text") or "").strip()
        if not text:
            _friendly_error(respond, "Usage: `/vendor add <name> [@owner]` or `/vendor update <name> stage=<stage> [quote=<amount>]` or `/vendor list`")
            return

        try:
            parts = shlex.split(text)
        except ValueError as e:
            _friendly_error(respond, f"Couldn't parse that: {e}")
            return
        sub = parts[0].lower()
        channel_id = command["channel_id"]

        with session_scope() as s:
            event = get_event_by_channel(s, channel_id)
            if not event:
                _friendly_error(respond, "No event in this channel. Use `/newevent` first.")
                return

            if sub == "list":
                vendors = s.scalars(select(Vendor).where(Vendor.event_id == event.id)).all()
                if not vendors:
                    respond({"response_type": "ephemeral", "text": "No vendors yet."})
                    return
                lines = []
                for v in vendors:
                    owner = f"<@{v.owner_user_id}>" if v.owner_user_id else "_unassigned_"
                    quote = f" — ${v.quote_amount:,.0f}" if v.quote_amount else ""
                    lines.append(f"• *{v.name}* ({v.stage.value}) — {owner}{quote}")
                respond({"response_type": "in_channel", "text": "*Vendors*\n" + "\n".join(lines)})
                return

            if sub == "add":
                if len(parts) < 2:
                    _friendly_error(respond, "Usage: `/vendor add <name> [@owner]`")
                    return
                owner_id = None
                name_parts = []
                for p in parts[1:]:
                    import re as _re
                    m = _re.match(r"^<@([UW][A-Z0-9]+)(\|[^>]+)?>$", p)
                    if m:
                        owner_id = m.group(1)
                    else:
                        name_parts.append(p)
                name = " ".join(name_parts).strip()
                if not name:
                    _friendly_error(respond, "Vendor name is required.")
                    return
                v = Vendor(event_id=event.id, name=name, owner_user_id=owner_id)
                s.add(v)
                owner = f"<@{owner_id}>" if owner_id else "_unassigned_"
                respond({"response_type": "in_channel", "text": f"Added vendor *{name}* ({owner})."})
                return

            if sub == "update":
                if len(parts) < 2:
                    _friendly_error(respond, "Usage: `/vendor update <name> stage=<stage> [quote=<amount>]`")
                    return
                kv = {}
                name_parts = []
                for p in parts[1:]:
                    if "=" in p:
                        k, _, val = p.partition("=")
                        kv[k.strip().lower()] = val.strip()
                    else:
                        name_parts.append(p)
                name = " ".join(name_parts).strip()
                v = find_vendor_by_name(s, event.id, name)
                if not v:
                    _friendly_error(respond, f"No vendor named `{name}`.")
                    return
                if "stage" in kv:
                    try:
                        v.stage = VendorStage(kv["stage"])
                    except ValueError:
                        valid = ", ".join(x.value for x in VendorStage)
                        _friendly_error(respond, f"Invalid stage. Try one of: {valid}")
                        return
                if "quote" in kv:
                    try:
                        v.quote_amount = float(kv["quote"].replace("$", "").replace(",", ""))
                    except ValueError:
                        _friendly_error(respond, f"Couldn't parse quote amount `{kv['quote']}`.")
                        return
                v.last_touch_at = datetime.utcnow()
                respond({"response_type": "in_channel",
                         "text": f"Updated *{v.name}* → stage *{v.stage.value}*"
                                 + (f", quote *${v.quote_amount:,.0f}*" if v.quote_amount else "")})
                return

            _friendly_error(respond, "Unknown subcommand. Try `add`, `update`, or `list`.")
