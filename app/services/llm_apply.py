"""Apply a confirmed PendingUpdate to the DB."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from app.db import session_scope
from app.models import (
    PendingUpdate, Task, TaskStatus, Vendor, VendorStage, BudgetLine, BudgetState, Event,
)
from app.services.events import find_task_by_fuzzy_title, find_vendor_by_name

log = logging.getLogger("pab.llm_apply")


def build_pending_summary(parsed: dict) -> list[str]:
    """Human-readable lines describing what Confirm will do."""
    out: list[str] = []
    if parsed.get("_error"):
        out.append(f"⚠️ Parse error: {parsed['_error']}")
        return out
    tu = parsed.get("task_update") or {}
    if tu and tu.get("task_match"):
        bits = [f"Task matching `{tu['task_match']}`"]
        if tu.get("status"):
            bits.append(f"→ status *{tu['status']}*")
        if tu.get("blocked_reason"):
            bits.append(f"(reason: {tu['blocked_reason']})")
        out.append("• " + " ".join(bits))
    vu = parsed.get("vendor_update") or {}
    if vu and vu.get("name"):
        bits = [f"Vendor *{vu['name']}*"]
        if vu.get("stage"):
            bits.append(f"→ stage *{vu['stage']}*")
        if vu.get("quote_amount") is not None:
            bits.append(f"quote *${float(vu['quote_amount']):,.0f}*")
        out.append("• " + " ".join(bits))
    bl = parsed.get("budget_line") or {}
    if bl and bl.get("label") and bl.get("amount") is not None:
        out.append(f"• Budget line *{bl['label']}* — ${float(bl['amount']):,.0f} ({bl.get('state', 'estimated')})")
    if not out:
        out.append("_(nothing structured to apply — Confirm will be a no-op)_")
    return out


def apply_pending_update(pending_id: int) -> str:
    """Apply a PendingUpdate; return a human summary of what changed."""
    changes: list[str] = []
    with session_scope() as s:
        pending = s.get(PendingUpdate, pending_id)
        if not pending:
            return "_(already applied or discarded)_"
        try:
            parsed = json.loads(pending.parsed_json)
        except Exception:
            s.delete(pending)
            return "_(couldn't re-parse — discarded)_"
        event_id = pending.event_id

        tu = parsed.get("task_update") or {}
        if tu and tu.get("task_match"):
            t = find_task_by_fuzzy_title(s, event_id, tu["task_match"])
            if t:
                if tu.get("status"):
                    try:
                        t.status = TaskStatus(tu["status"])
                        changes.append(f"• Task *{t.title}* → *{t.status.value}*")
                    except ValueError:
                        pass
                if tu.get("blocked_reason"):
                    t.blocked_reason = tu["blocked_reason"]
            else:
                changes.append(f"• _(no task matched `{tu['task_match']}`)_")

        vu = parsed.get("vendor_update") or {}
        if vu and vu.get("name"):
            v = find_vendor_by_name(s, event_id, vu["name"])
            if not v:
                v = Vendor(event_id=event_id, name=vu["name"])
                s.add(v)
            if vu.get("stage"):
                try:
                    v.stage = VendorStage(vu["stage"])
                except ValueError:
                    pass
            if vu.get("quote_amount") is not None:
                try:
                    v.quote_amount = float(vu["quote_amount"])
                except (TypeError, ValueError):
                    pass
            v.last_touch_at = datetime.utcnow()
            parts = [f"• Vendor *{v.name}* → stage *{v.stage.value}*"]
            if v.quote_amount is not None:
                parts.append(f"(quote ${v.quote_amount:,.0f})")
            changes.append(" ".join(parts))

        bl = parsed.get("budget_line") or {}
        if bl and bl.get("label") and bl.get("amount") is not None:
            try:
                state = BudgetState(bl.get("state", "estimated"))
            except ValueError:
                state = BudgetState.estimated
            amount = float(bl["amount"])
            s.add(BudgetLine(event_id=event_id, label=bl["label"], amount=amount, state=state))
            changes.append(f"• Budget line *{bl['label']}* — ${amount:,.0f} ({state.value})")

        s.delete(pending)

    return "\n".join(changes) if changes else "_(no changes)_"


def store_pending(event_id: int, requested_by: str, raw_text: str, parsed: dict, channel_id: str | None) -> int:
    with session_scope() as s:
        p = PendingUpdate(
            event_id=event_id,
            requested_by=requested_by,
            raw_text=raw_text,
            parsed_json=json.dumps(parsed),
            channel_id=channel_id,
        )
        s.add(p)
        s.flush()
        return p.id
