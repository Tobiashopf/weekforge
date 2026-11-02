"""Data export: CSV for spreadsheets, JSON as a full backup. Pure reads."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timezone
from typing import Any, Iterable

from sqlmodel import Session, SQLModel, select

from app.models import Habit, HabitLog, HabitWeek, RecurringTask, Task, Week

EXPORT_VERSION = 1

# Spreadsheet apps run cells that start with these as formulas ("CSV injection").
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "sim" if value else "não"
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return "'" + value if value.startswith(_FORMULA_START) else value
    return str(value)


def to_csv(header: list[str], rows: Iterable[list[Any]]) -> str:
    buf = io.StringIO()
    buf.write("﻿")  # BOM: Excel then reads the file as UTF-8 (accents)
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_cell(v) for v in row])
    return buf.getvalue()


def tasks_csv(session: Session) -> str:
    rows = session.exec(
        select(Task, Week).where(Task.week_id == Week.id).order_by(Week.start_date, Task.day, Task.due_time, Task.id)
    ).all()
    return to_csv(
        ["semana", "dia", "horario", "titulo", "feita", "levada_para_proxima", "recorrente"],
        ([w.start_date, t.day, t.due_time, t.title, t.done, t.carried, t.recurring_id is not None] for t, w in rows),
    )


def habits_csv(session: Session) -> str:
    habits = {h.id: h for h in session.exec(select(Habit)).all()}
    logs = session.exec(select(HabitLog).order_by(HabitLog.day, HabitLog.habit_id)).all()
    minutes = session.exec(
        select(HabitWeek, Week).where(HabitWeek.week_id == Week.id).order_by(Week.start_date, HabitWeek.habit_id)
    ).all()

    def rows():
        for log in logs:
            h = habits.get(log.habit_id)
            if h is None:
                continue
            target = max(h.daily_target, 1)
            yield [log.day, h.name, h.kind.value, log.value, target, log.value >= target, ""]
        for hw, week in minutes:
            h = habits.get(hw.habit_id)
            if h is not None and hw.minutes:
                yield [week.start_date, h.name, "minutos_semana", "", "", "", hw.minutes]

    return to_csv(["data", "habito", "tipo", "valor", "meta", "cumpriu", "minutos_semana"], rows())


def _dump(obj: SQLModel) -> dict:
    out = {}
    for key, value in obj.model_dump().items():
        if isinstance(value, time):
            value = value.strftime("%H:%M")
        elif isinstance(value, (date, datetime)):
            value = value.isoformat()
        elif hasattr(value, "value"):  # enums
            value = value.value
        out[key] = value
    return out


def full_backup(session: Session) -> dict:
    """Everything, as plain JSON types. Ids are kept so references between tables survive."""
    def all_of(model):
        return [_dump(o) for o in session.exec(select(model).order_by(model.id)).all()]

    return {
        "app": "weekforge",
        "version": EXPORT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "weeks": all_of(Week),
        "tasks": all_of(Task),
        "recurring_tasks": all_of(RecurringTask),
        "habits": all_of(Habit),
        "habit_logs": all_of(HabitLog),
        "habit_weeks": all_of(HabitWeek),
    }
