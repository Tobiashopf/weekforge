"""Week logic: finding weeks and computing performance."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlmodel import Session, select

from app.models import Task, Week

DAY_LABELS = ["DOM", "SEG", "TER", "QUA", "QUI", "SEX", "SÁB"]


def week_start(d: date) -> date:
    """Return the Sunday that starts the week containing `d`."""
    # date.weekday(): Monday=0 ... Sunday=6
    return d - timedelta(days=(d.weekday() + 1) % 7)


def get_or_create_week(session: Session, d: date) -> Week:
    start = week_start(d)
    week = session.exec(select(Week).where(Week.start_date == start)).first()
    if week is None:
        week = Week(start_date=start)
        session.add(week)
        session.commit()
        session.refresh(week)
    return week


def week_days(week: Week) -> list[tuple[str, date]]:
    return [(DAY_LABELS[i], week.start_date + timedelta(days=i)) for i in range(7)]


@dataclass
class Performance:
    done: int
    pending: int

    @property
    def total(self) -> int:
        return self.done + self.pending

    @property
    def done_pct(self) -> int:
        return round(100 * self.done / self.total) if self.total else 0

    @property
    def pending_pct(self) -> int:
        return 100 - self.done_pct if self.total else 0


def week_performance(session: Session, week: Week) -> Performance:
    tasks = session.exec(
        select(Task).where(Task.week_id == week.id, Task.day.is_not(None))
    ).all()
    done = sum(1 for t in tasks if t.done)
    return Performance(done=done, pending=len(tasks) - done)
