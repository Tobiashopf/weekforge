"""Week logic: finding weeks and computing performance."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.models import Habit, HabitKind, HabitLog, HabitWeek, RecurringTask, Task, Week

DAY_LABELS = ["DOM", "SEG", "TER", "QUA", "QUI", "SEX", "SÁB"]


def week_start(d: date) -> date:
    """Return the Sunday that starts the week containing `d`."""
    # date.weekday(): Monday=0 ... Sunday=6
    return d - timedelta(days=(d.weekday() + 1) % 7)


def today() -> date:
    """Current date; a function so tests can pin it."""
    return date.today()


def get_or_create_week(session: Session, d: date) -> Week:
    start = week_start(d)
    week = session.exec(select(Week).where(Week.start_date == start)).first()
    if week is None:
        week = Week(start_date=start)
        session.add(week)
        session.commit()
        session.refresh(week)
        # A new week gets its recurring tasks (never back-filled into past days).
        for rule in session.exec(select(RecurringTask)).all():
            apply_rule_to_week(session, rule, week)
        session.commit()
    return week


def week_days(week: Week) -> list[tuple[str, date]]:
    return [(DAY_LABELS[i], week.start_date + timedelta(days=i)) for i in range(7)]


@dataclass
class Performance:
    done: int
    pending: int
    week_id: Optional[int] = None
    carried: int = 0  # pending tasks already copied to next week (still count as pending)
    carryable: int = 0  # unfinished tasks (agenda + to-do) not yet carried

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
    tasks = session.exec(select(Task).where(Task.week_id == week.id)).all()
    scheduled = [t for t in tasks if t.day is not None]
    done = sum(1 for t in scheduled if t.done)
    return Performance(
        done=done,
        pending=len(scheduled) - done,
        week_id=week.id,
        carried=sum(1 for t in scheduled if t.carried),
        carryable=sum(1 for t in tasks if not t.done and not t.carried and t.recurring_id is None),
    )


def carry_over(session: Session, week: Week) -> tuple[Week, int]:
    """Bring unfinished work into the next week's to-do list.

    - Unfinished agenda tasks are copied (title and time) and the original is marked
      `carried`, so this week's score still shows them as not done.
    - Unfinished to-do items have no day and don't affect the score: they are moved.
    Running it twice does nothing the second time.
    """
    next_week = get_or_create_week(session, week.start_date + timedelta(days=7))
    tasks = session.exec(
        select(Task).where(
            Task.week_id == week.id,
            Task.done == False,  # noqa: E712
            Task.carried == False,  # noqa: E712
            Task.recurring_id.is_(None),  # recurring tasks come back on their own
        )
    ).all()
    for task in sort_tasks(tasks):
        if task.day is None:
            task.week_id = next_week.id
        else:
            session.add(Task(week_id=next_week.id, title=task.title, due_time=task.due_time))
            task.carried = True
        session.add(task)
    session.commit()
    return next_week, len(tasks)


# --- task time ---------------------------------------------------------------

_QUICK_TIME = re.compile(r"^\s*(\d{1,2})(?::(\d{2})|h(\d{2})?)\s+(.+)$", re.IGNORECASE)


def parse_quick_time(title: str) -> tuple[Optional[time], str]:
    """'14h Reunião' / '9:30 Médico' / '7h30 Treino' -> (time, rest of title).

    Requires ':' or 'h' after the hour so titles like '3 livros' stay untouched.
    """
    m = _QUICK_TIME.match(title)
    if not m:
        return None, title.strip()
    hour = int(m.group(1))
    minute = int(m.group(2) or m.group(3) or 0)
    if hour > 23 or minute > 59:
        return None, title.strip()
    return time(hour, minute), m.group(4).strip()


def sort_tasks(tasks: list[Task]) -> list[Task]:
    """Timed tasks first, in time order; untimed after, in creation order."""
    return sorted(tasks, key=lambda t: (t.due_time is None, t.due_time or time.min, t.id or 0))


# --- recurring tasks ------------------------------------------------------------


def apply_rule_to_week(session: Session, rule: RecurringTask, week: Week) -> int:
    """Create the rule's tasks in `week`, from today on. Skips days that already have one."""
    created = 0
    for i in rule.day_indexes:
        d = week.start_date + timedelta(days=i)
        if d < today():
            continue
        exists = session.exec(
            select(Task).where(Task.recurring_id == rule.id, Task.day == d)
        ).first()
        if exists is None:
            session.add(
                Task(week_id=week.id, title=rule.title, day=d, due_time=rule.due_time, recurring_id=rule.id)
            )
            created += 1
    return created


def create_rule(session: Session, title: str, weekdays: list[int]) -> RecurringTask:
    """Save a rule and fill the current week (from today) and any future weeks already open."""
    due_time, clean = parse_quick_time(title)
    rule = RecurringTask(
        title=clean, due_time=due_time, weekdays=",".join(str(i) for i in sorted(set(weekdays)))
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    current = get_or_create_week(session, today())
    weeks = session.exec(select(Week).where(Week.start_date >= current.start_date)).all()
    for week in weeks:
        apply_rule_to_week(session, rule, week)
    session.commit()
    return rule


def delete_rule(session: Session, rule: RecurringTask) -> int:
    """Delete a rule and its unfinished tasks from today on; past and done ones stay as history."""
    removed = 0
    for task in session.exec(select(Task).where(Task.recurring_id == rule.id)).all():
        if not task.done and task.day is not None and task.day >= today():
            session.delete(task)
            removed += 1
        else:
            task.recurring_id = None
            session.add(task)
    session.delete(rule)
    session.commit()
    return removed


WEEKDAY_LETTERS = ["D", "S", "T", "Q", "Q", "S", "S"]


def describe_weekdays(indexes: list[int]) -> str:
    if indexes == list(range(7)):
        return "Todo dia"
    if indexes == [1, 2, 3, 4, 5]:
        return "Seg a sex"
    if indexes == [0, 6]:
        return "Fins de semana"
    return ", ".join(DAY_LABELS[i].capitalize() for i in indexes)


# --- habits ---------------------------------------------------------------------

DEFAULT_HABITS = [
    ("Meditação", "🧘", HabitKind.check, 1),
    ("Leitura", "📖", HabitKind.check, 1),
    ("Atividade física", "🏋️", HabitKind.check, 1),
    ("Inglês", "🗣️", HabitKind.check, 1),
    ("Estudar", "📚", HabitKind.check, 1),
    ("Água", "💧", HabitKind.counter, 8),
]


def seed_default_habits(session: Session) -> None:
    """First run only: the table is empty. Habits are archived, never deleted, so it stays non-empty."""
    if session.exec(select(Habit)).first() is not None:
        return
    for name, emoji, kind, target in DEFAULT_HABITS:
        session.add(Habit(name=name, emoji=emoji, kind=kind, daily_target=target))
    session.commit()


@dataclass
class HabitCell:
    day: date
    value: int
    future: bool
    met: bool


@dataclass
class HabitRow:
    habit: Habit
    week: Week
    cells: list[HabitCell]
    minutes: int

    @property
    def days_met(self) -> int:
        return sum(1 for c in self.cells if c.met)


def habit_row(session: Session, habit: Habit, week: Week) -> HabitRow:
    end = week.start_date + timedelta(days=6)
    logs = {
        log.day: log.value
        for log in session.exec(
            select(HabitLog).where(
                HabitLog.habit_id == habit.id, HabitLog.day >= week.start_date, HabitLog.day <= end
            )
        ).all()
    }
    target = max(habit.daily_target, 1)
    cells = []
    for i in range(7):
        d = week.start_date + timedelta(days=i)
        value = logs.get(d, 0)
        cells.append(HabitCell(day=d, value=value, future=d > today(), met=value >= target))
    hw = session.exec(
        select(HabitWeek).where(HabitWeek.habit_id == habit.id, HabitWeek.week_id == week.id)
    ).first()
    return HabitRow(habit=habit, week=week, cells=cells, minutes=hw.minutes if hw else 0)


def habit_rows(session: Session, week: Week) -> list[HabitRow]:
    habits = session.exec(select(Habit).where(Habit.active == True).order_by(Habit.id)).all()  # noqa: E712
    return [habit_row(session, h, week) for h in habits]


def log_habit(session: Session, habit: Habit, d: date, action: str) -> HabitLog:
    """action: 'toggle' (check habits), 'inc' / 'dec' (counter habits)."""
    log = session.exec(select(HabitLog).where(HabitLog.habit_id == habit.id, HabitLog.day == d)).first()
    if log is None:
        log = HabitLog(habit_id=habit.id, day=d, value=0)
    if action == "toggle":
        log.value = 0 if log.value else 1
    elif action == "inc":
        log.value = min(log.value + 1, 99)
    elif action == "dec":
        log.value = max(log.value - 1, 0)
    else:
        raise ValueError(action)
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


def set_habit_minutes(session: Session, habit: Habit, week: Week, minutes: int) -> None:
    hw = session.exec(
        select(HabitWeek).where(HabitWeek.habit_id == habit.id, HabitWeek.week_id == week.id)
    ).first() or HabitWeek(habit_id=habit.id, week_id=week.id)
    hw.minutes = minutes
    session.add(hw)
    session.commit()
