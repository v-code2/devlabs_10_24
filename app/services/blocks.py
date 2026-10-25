"""Block Kit builders for messages and modals."""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.models import Event, Task, TaskStatus, BudgetLine, BudgetState, Vendor, VendorStage


def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _divider() -> dict:
    return {"type": "divider"}


def _header(text: str) -> dict:
    return {"type": "header", "text": {"type": "plain_text", "text": text[:150]}}


# ---------- Modals ----------

def new_event_modal() -> dict:
    return {
        "type": "modal",
        "callback_id": "new_event_submit",
        "title": {"type": "plain_text", "text": "New event"},
        "submit": {"type": "plain_text", "text": "Create"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "name",
                "label": {"type": "plain_text", "text": "Event name"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "val",
                    "placeholder": {"type": "plain_text", "text": "Homecoming Mixer"},
                },
            },
            {
                "type": "input",
                "block_id": "event_date",
                "label": {"type": "plain_text", "text": "Event date"},
                "element": {"type": "datepicker", "action_id": "val"},
            },
            {
                "type": "input",
                "block_id": "budget",
                "label": {"type": "plain_text", "text": "Total budget (USD)"},
                "element": {
                    "type": "number_input",
                    "is_decimal_allowed": True,
                    "action_id": "val",
                    "placeholder": {"type": "plain_text", "text": "2000"},
                },
            },
            {
                "type": "input",
                "block_id": "channel",
                "label": {"type": "plain_text", "text": "Event channel"},
                "element": {
                    "type": "channels_select",
                    "action_id": "val",
                    "placeholder": {"type": "plain_text", "text": "Pick a channel"},
                },
            },
        ],
    }


def blocked_reason_modal(task_id: int, trigger_channel: Optional[str] = None) -> dict:
    return {
        "type": "modal",
        "callback_id": "blocked_reason_submit",
        "private_metadata": f"{task_id}|{trigger_channel or ''}",
        "title": {"type": "plain_text", "text": "What's blocking?"},
        "submit": {"type": "plain_text", "text": "Send"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "reason",
                "label": {"type": "plain_text", "text": "Describe the blocker"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "val",
                    "multiline": True,
                },
            }
        ],
    }


def changes_requested_modal(task_id: int) -> dict:
    return {
        "type": "modal",
        "callback_id": "changes_requested_submit",
        "private_metadata": str(task_id),
        "title": {"type": "plain_text", "text": "Request changes"},
        "submit": {"type": "plain_text", "text": "Send"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "feedback",
                "label": {"type": "plain_text", "text": "What should change?"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "val",
                    "multiline": True,
                },
            }
        ],
    }


# ---------- Event summary ----------

def event_summary(event: Event, tasks: list[Task]) -> list[dict]:
    rff = event.rff_deadline.isoformat() if event.rff_deadline else "—"
    director = f"<@{event.director_user_id}>" if event.director_user_id else "—"
    lines = [
        f"*{event.name}*",
        f"Date: *{event.event_date.isoformat()}*  •  Budget: *${event.total_budget:,.0f}*",
        f"RFF deadline: *{rff}*  •  Director: {director}",
    ]
    blocks = [
        _header("Event timeline"),
        _section("\n".join(lines)),
        _divider(),
        _section("*Milestones*"),
    ]
    for t in sorted(tasks, key=lambda x: (x.due_date or date.max)):
        owner = f"<@{t.owner_user_id}>" if t.owner_user_id else "_unassigned_"
        due = t.due_date.isoformat() if t.due_date else "—"
        approval = "  🔒 _needs approval_" if t.needs_approval else ""
        blocks.append(_section(f"• `{due}`  {t.title} — {owner}{approval}"))
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": "I'll DM owners before due dates. Ask me anything by `@`-mentioning me."}
        ],
    })
    return blocks


# ---------- /status ----------

def status_blocks(event: Event, tasks: list[Task], today: date) -> list[dict]:
    buckets = {s: [] for s in TaskStatus}
    overdue = []
    for t in tasks:
        buckets[t.status].append(t)
        if t.status != TaskStatus.done and t.due_date and t.due_date < today:
            overdue.append(t)

    def fmt(t: Task) -> str:
        owner = f"<@{t.owner_user_id}>" if t.owner_user_id else "_unassigned_"
        due = t.due_date.isoformat() if t.due_date else "—"
        return f"• `{due}`  {t.title} — {owner}"

    blocks: list[dict] = [_header(f"Status — {event.name}")]
    if overdue:
        blocks.append(_section("*⚠️ Overdue*\n" + "\n".join(fmt(t) for t in overdue)))
    if buckets[TaskStatus.in_progress]:
        blocks.append(_section("*In progress*\n" + "\n".join(fmt(t) for t in buckets[TaskStatus.in_progress])))
    if buckets[TaskStatus.blocked]:
        blocks.append(_section("*🚧 Blocked*\n" + "\n".join(fmt(t) for t in buckets[TaskStatus.blocked])))
    if buckets[TaskStatus.todo]:
        upcoming = [t for t in buckets[TaskStatus.todo] if t not in overdue]
        if upcoming:
            blocks.append(_section("*To do*\n" + "\n".join(fmt(t) for t in sorted(upcoming, key=lambda x: (x.due_date or date.max))[:10])))
    if buckets[TaskStatus.done]:
        blocks.append(_section(f"*✅ Done* — {len(buckets[TaskStatus.done])}"))
    return blocks


# ---------- /budget ----------

def budget_blocks(event: Event, lines: list[BudgetLine]) -> list[dict]:
    totals = {BudgetState.estimated: 0.0, BudgetState.committed: 0.0, BudgetState.spent: 0.0}
    for b in lines:
        totals[b.state] += b.amount
    est = totals[BudgetState.estimated]
    com = totals[BudgetState.committed]
    spent = totals[BudgetState.spent]
    remaining = event.total_budget - (com + spent)
    warn = ""
    if (com + spent + est) > event.total_budget:
        warn = f"\n⚠️ *Estimated + committed + spent exceeds budget by ${(com + spent + est) - event.total_budget:,.0f}*"

    body = (
        f"*{event.name}* — total budget *${event.total_budget:,.0f}*\n"
        f"Estimated: *${est:,.0f}*\n"
        f"Committed: *${com:,.0f}*\n"
        f"Spent: *${spent:,.0f}*\n"
        f"Remaining (budget − committed − spent): *${remaining:,.0f}*"
        f"{warn}"
    )
    blocks = [_header("Budget"), _section(body)]
    if lines:
        rows = "\n".join(
            f"• {b.label} — ${b.amount:,.0f}  _({b.state.value})_" for b in lines
        )
        blocks.append(_section("*Line items*\n" + rows))
    return blocks


# ---------- Nudge DM ----------

def nudge_dm(task: Task, event: Event, tone: str) -> list[dict]:
    due = task.due_date.isoformat() if task.due_date else "—"
    greetings = {
        "gentle": f"Hey! Checking in on *{task.title}* for *{event.name}*. Due *{due}*. How's it going?",
        "firmer": f"Hi again — *{task.title}* for *{event.name}* is due *{due}*. Where are we?",
        "final": f"⚠️ Last check: *{task.title}* for *{event.name}* was due *{due}* and I'm escalating to the director if I don't hear back.",
    }
    text = greetings.get(tone, greetings["gentle"])
    return [
        _section(text),
        {
            "type": "actions",
            "block_id": f"nudge_task_{task.id}",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "Done"}, "style": "primary", "action_id": "nudge_done", "value": str(task.id)},
                {"type": "button", "text": {"type": "plain_text", "text": "In progress"}, "action_id": "nudge_in_progress", "value": str(task.id)},
                {"type": "button", "text": {"type": "plain_text", "text": "Blocked"}, "style": "danger", "action_id": "nudge_blocked", "value": str(task.id)},
            ],
        },
    ]


# ---------- Approval DM ----------

def approval_dm(task: Task, event: Event) -> list[dict]:
    owner = f"<@{task.owner_user_id}>" if task.owner_user_id else "the owner"
    text = f"Approval needed: *{task.title}* for *{event.name}* ({owner}). Does this look good?"
    return [
        _section(text),
        {
            "type": "actions",
            "block_id": f"approval_task_{task.id}",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "Approve"}, "style": "primary", "action_id": "approval_approve", "value": str(task.id)},
                {"type": "button", "text": {"type": "plain_text", "text": "Request changes"}, "action_id": "approval_changes", "value": str(task.id)},
            ],
        },
    ]


# ---------- Pending update confirmation ----------

def pending_update_blocks(pending_id: int, raw_text: str, summary_lines: list[str]) -> list[dict]:
    return [
        _section(f"I parsed: _{raw_text}_"),
        _section("\n".join(summary_lines) or "_(no changes detected)_"),
        {
            "type": "actions",
            "block_id": f"pending_{pending_id}",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "Confirm"}, "style": "primary", "action_id": "pending_confirm", "value": str(pending_id)},
                {"type": "button", "text": {"type": "plain_text", "text": "Edit"}, "action_id": "pending_edit", "value": str(pending_id)},
                {"type": "button", "text": {"type": "plain_text", "text": "Discard"}, "style": "danger", "action_id": "pending_discard", "value": str(pending_id)},
            ],
        },
    ]
