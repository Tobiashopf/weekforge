"""Data models for Weekforge."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class Week(SQLModel, table=True):
    """One planning week, identified by its Sunday start date."""

    id: Optional[int] = Field(default=None, primary_key=True)
    start_date: date = Field(index=True, unique=True)  # always a Sunday
    focus_word: str = ""
    notes: str = ""
    reminders: str = ""


class Task(SQLModel, table=True):
    """A task. With `day` set it lives in the week agenda; without it, in the backlog."""

    id: Optional[int] = Field(default=None, primary_key=True)
    week_id: int = Field(foreign_key="week.id", index=True)
    title: str
    day: Optional[date] = None
    due_time: Optional[time] = None
    done: bool = False
    carried: bool = False  # copied to the next week's to-do as unfinished
    recurring_id: Optional[int] = Field(default=None, index=True)  # set if created by a RecurringTask
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RecurringTask(SQLModel, table=True):
    """A rule that creates a task on the chosen weekdays of every week."""

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    due_time: Optional[time] = None
    weekdays: str  # comma-separated indexes, 0 = Sunday ... 6 = Saturday, e.g. "1,3,5"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def day_indexes(self) -> list[int]:
        return sorted(int(x) for x in self.weekdays.split(",") if x != "")


class HabitKind(str, Enum):
    check = "check"      # done / not done, optionally with minutes
    counter = "counter"  # e.g. glasses of water


class Habit(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    kind: HabitKind = HabitKind.check
    daily_target: int = 1  # counter target, or minutes goal for check habits
    active: bool = True


class HabitLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    habit_id: int = Field(foreign_key="habit.id", index=True)
    day: date = Field(index=True)
    value: int = 0  # 1 = done for check habits, count for counters
    minutes: int = 0
