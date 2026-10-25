from __future__ import annotations

import enum
from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import (
    String, Integer, Float, Date, DateTime, Enum, ForeignKey, Boolean, Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class EventStatus(str, enum.Enum):
    planning = "planning"
    active = "active"
    done = "done"
    cancelled = "cancelled"


class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"


class BudgetState(str, enum.Enum):
    estimated = "estimated"
    committed = "committed"
    spent = "spent"


class VendorStage(str, enum.Enum):
    not_contacted = "not_contacted"
    contacted = "contacted"
    replied = "replied"
    quote_received = "quote_received"
    chosen = "chosen"


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    channel_id: Mapped[str] = mapped_column(String(32), unique=True)
    event_date: Mapped[date] = mapped_column(Date)
    total_budget: Mapped[float] = mapped_column(Float, default=0.0)
    rff_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    director_user_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus), default=EventStatus.planning)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tasks: Mapped[List["Task"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    budget_lines: Mapped[List["BudgetLine"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    vendors: Mapped[List["Vendor"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    title: Mapped[str] = mapped_column(String(300))
    owner_user_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.todo)
    last_nudged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    nudge_count: Mapped[int] = mapped_column(Integer, default=0)
    needs_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approver_user_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approval_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    event: Mapped[Event] = relationship(back_populates="tasks")


class BudgetLine(Base):
    __tablename__ = "budget_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    label: Mapped[str] = mapped_column(String(200))
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    state: Mapped[BudgetState] = mapped_column(Enum(BudgetState), default=BudgetState.estimated)
    vendor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vendors.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    event: Mapped[Event] = relationship(back_populates="budget_lines")


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    name: Mapped[str] = mapped_column(String(200))
    owner_user_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    stage: Mapped[VendorStage] = mapped_column(Enum(VendorStage), default=VendorStage.not_contacted)
    quote_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_touch_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    event: Mapped[Event] = relationship(back_populates="vendors")


class NudgeLog(Base):
    """Idempotency: one row per (task, user, day). Prevents double-DMs after restart."""
    __tablename__ = "nudge_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    user_id: Mapped[str] = mapped_column(String(32))
    day: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(32))  # "nudge" | "escalation" | "approval"
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PendingUpdate(Base):
    """Parsed-but-unconfirmed LLM updates awaiting Confirm/Edit."""
    __tablename__ = "pending_updates"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    requested_by: Mapped[str] = mapped_column(String(32))
    raw_text: Mapped[str] = mapped_column(Text)
    parsed_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    channel_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
