"""Anthropic-powered parsing and grounded Q&A.

Two entry points:
- parse_update(raw_text, snapshot): return structured JSON (vendor/amount/stage/task updates)
- answer_question(question, snapshot): return a short answer grounded ONLY in snapshot data
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from anthropic import Anthropic

from app.config import config

log = logging.getLogger("pab.llm")

_client: Optional[Anthropic] = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=config.anthropic_api_key)
    return _client


PARSE_SYSTEM = """You convert plain-language updates from student-org members into structured JSON.

Return ONLY valid JSON. No prose, no code fences. Schema:
{
  "task_update": {"task_match": "<fuzzy title words to match a task>", "status": "todo|in_progress|blocked|done" | null, "blocked_reason": "<string>" | null} | null,
  "vendor_update": {
    "name": "<vendor name>" | null,
    "stage": "not_contacted|contacted|replied|quote_received|chosen" | null,
    "quote_amount": <number> | null
  } | null,
  "budget_line": {"label": "<string>", "amount": <number>, "state": "estimated|committed|spent"} | null,
  "notes": "<optional short clarification>"
}

Rules:
- Omit fields you can't infer; use null instead of guessing.
- Dollar amounts: strip $ and commas, return a number.
- If the sentence mentions getting a quote with an amount from a vendor, set
  vendor_update.stage="quote_received", vendor_update.quote_amount=<amount>, and
  budget_line.state="estimated" with label like "<Vendor> quote".
- Don't invent vendors, amounts, or task titles that aren't in the sentence.
"""

ANSWER_SYSTEM = """You answer questions about a student-org event using ONLY the JSON snapshot provided.

Rules:
- Base every claim strictly on the snapshot. If the snapshot does not contain the answer, say so plainly ("I don't have that in the event data").
- Never invent dates, amounts, names, or owners.
- Be concise: 1-3 short sentences. Dates in YYYY-MM-DD. Dollar amounts with $ and no decimals.
- When you reference a person, use Slack-style <@USERID> if an ID is given in the snapshot.
- Today's date is in snapshot.event.today — use it to describe "overdue" or "in N days".
"""


def _extract_text(resp) -> str:
    parts = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts).strip()


def parse_update(raw_text: str, snapshot: dict) -> dict:
    client = _get_client()
    user_msg = (
        "Snapshot (for context — vendor/task names available):\n"
        f"{json.dumps(snapshot, default=str)}\n\n"
        f"Update: {raw_text}"
    )
    try:
        resp = client.messages.create(
            model=config.anthropic_model,
            max_tokens=600,
            system=PARSE_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
    except Exception as e:
        log.exception("Anthropic parse_update failed")
        return {"_error": str(e)}

    text = _extract_text(resp)
    # Strip accidental code fences just in case.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.DOTALL)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.warning("Non-JSON parse_update output: %r", text)
        return {"_error": "LLM returned non-JSON", "_raw": text}


def answer_question(question: str, snapshot: dict) -> str:
    client = _get_client()
    user_msg = (
        f"Snapshot:\n{json.dumps(snapshot, default=str)}\n\n"
        f"Question: {question}"
    )
    try:
        resp = client.messages.create(
            model=config.anthropic_model,
            max_tokens=400,
            system=ANSWER_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
    except Exception as e:
        log.exception("Anthropic answer_question failed")
        return f"I hit an error reaching the LLM: {e}"
    return _extract_text(resp) or "I don't have an answer in the event data."
