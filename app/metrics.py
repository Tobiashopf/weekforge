"""Numbers for the metrics page. Pure reads, no writes."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.models import Habit, HabitKind, HabitLog, HabitWeek, Task, Week
from app import services
from app.services import DAY_LABELS, week_start


def today() -> date:
    return services.today()  # looked up at call time so tests can pin the date


def _pct(done: int, total: int) -> Optional[int]:
    return round(100 * done / total) if total else None


# --- tasks --------------------------------------------------------------------


@dataclass
class WeekRate:
    start: date
    done: int
    total: int

    @property
    def pct(self) -> Optional[int]:
        return _pct(self.done, self.total)


def weekly_completion(session: Session, weeks: int) -> list[WeekRate]:
    """Completion of scheduled tasks for the last `weeks` weeks, oldest first (current week last)."""
    current = week_start(today())
    first = current - timedelta(weeks=weeks - 1)
    counts: dict[date, list[int]] = {first + timedelta(weeks=i): [0, 0] for i in range(weeks)}
    rows = session.exec(
        select(Task, Week).where(Task.week_id == Week.id, Task.day.is_not(None), Week.start_date >= first)
    ).all()
    for task, week in rows:
        if week.start_date in counts:
            counts[week.start_date][1] += 1
            counts[week.start_date][0] += int(task.done)
    return [WeekRate(start=s, done=d, total=t) for s, (d, t) in counts.items()]


@dataclass
class WeekdayRate:
    label: str
    done: int
    total: int

    @property
    def pct(self) -> Optional[int]:
        return _pct(self.done, self.total)


def weekday_completion(session: Session, weeks: int) -> list[WeekdayRate]:
    """Completion per weekday (Sunday first) over the same window, past days only."""
    first = week_start(today()) - timedelta(weeks=weeks - 1)
    done, total = [0] * 7, [0] * 7
    tasks = session.exec(select(Task).where(Task.day.is_not(None), Task.day >= first, Task.day <= today())).all()
    for t in tasks:
        i = (t.day.weekday() + 1) % 7
        total[i] += 1
        done[i] += int(t.done)
    return [WeekdayRate(DAY_LABELS[i], done[i], total[i]) for i in range(7)]


# --- habits ---------------------------------------------------------------------


def _met_days(session: Session, habit: Habit) -> set[date]:
    target = max(habit.daily_target, 1)
    logs = session.exec(select(HabitLog).where(HabitLog.habit_id == habit.id)).all()
    return {log.day for log in logs if log.value >= target and log.day <= today()}


def streaks(met: set[date]) -> tuple[int, int]:
    """(current, best). The current streak may end yesterday: today isn't over yet."""
    best = run = 0
    prev = None
    for d in sorted(met):
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    current = 0
    d = today() if today() in met else today() - timedelta(days=1)
    while d in met:
        current += 1
        d -= timedelta(days=1)
    return current, best


@dataclass
class HabitStats:
    habit: Habit
    current_streak: int
    best_streak: int
    met_last_30: int
    avg: Optional[float]  # check: minutes/week over weeks with time logged; counter: count/day, last 30 days
    avg_unit: str


def habit_stats(session: Session, weeks: int) -> list[HabitStats]:
    habits = session.exec(select(Habit).where(Habit.active == True).order_by(Habit.id)).all()  # noqa: E712
    since = today() - timedelta(days=29)
    first_week = week_start(today()) - timedelta(weeks=weeks - 1)
    out = []
    for h in habits:
        met = _met_days(session, h)
        current, best = streaks(met)
        last_30 = sum(1 for d in met if d >= since)
        if h.kind == HabitKind.check:
            minutes = [
                hw.minutes
                for hw, wk in session.exec(
                    select(HabitWeek, Week).where(
                        HabitWeek.week_id == Week.id, HabitWeek.habit_id == h.id, Week.start_date >= first_week
                    )
                ).all()
                if hw.minutes > 0
            ]
            avg, unit = (round(sum(minutes) / len(minutes)) if minutes else None), "min/semana"
        else:
            logs = session.exec(
                select(HabitLog).where(HabitLog.habit_id == h.id, HabitLog.day >= since, HabitLog.day <= today())
            ).all()
            avg, unit = round(sum(log.value for log in logs) / 30, 1), "/dia (30 dias)"
        out.append(HabitStats(h, current, best, last_30, avg, unit))
    return out


# --- year heatmap ------------------------------------------------------------------

HEAT_STEPS = [0, 1, 3, 5, 7]  # lower bound of each level 0..4


@dataclass
class HeatCell:
    day: date
    count: int
    future: bool

    @property
    def level(self) -> int:
        return max(i for i, low in enumerate(HEAT_STEPS) if self.count >= low)


def year_heatmap(session: Session) -> list[list[Optional[HeatCell]]]:
    """53 week columns (Sunday-first) ending this week; each day counts tasks done + habits met."""
    end = week_start(today()) + timedelta(days=6)
    start = week_start(today()) - timedelta(weeks=52)
    counts: dict[date, int] = defaultdict(int)
    for t in session.exec(select(Task).where(Task.done == True, Task.day >= start)).all():  # noqa: E712
        counts[t.day] += 1
    targets = {h.id: max(h.daily_target, 1) for h in session.exec(select(Habit)).all()}
    for log in session.exec(select(HabitLog).where(HabitLog.day >= start)).all():
        if log.value >= targets.get(log.habit_id, 1):
            counts[log.day] += 1
    columns = []
    d = start
    while d <= end:
        col = []
        for i in range(7):
            day = d + timedelta(days=i)
            col.append(HeatCell(day, counts.get(day, 0), day > today()))
        columns.append(col)
        d += timedelta(weeks=1)
    return columns


def month_labels(columns: list[list[HeatCell]]) -> list[tuple[int, str]]:
    """(column index, 'nov') where a new month starts."""
    names = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    out, last = [], None
    for i, col in enumerate(columns):
        m = col[0].day.month
        if m != last:
            out.append((i, names[m - 1]))
            last = m
    # drop labels too close to the next one (first column) or to the right edge
    out = [(i, name) for k, (i, name) in enumerate(out)
           if (k + 1 >= len(out) or out[k + 1][0] - i >= 3) and i <= len(columns) - 3]
    return out
