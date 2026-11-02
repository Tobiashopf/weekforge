"""Weekforge web app."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app import db as _db
from app.db import get_session, init_db
from app.models import Habit, HabitKind, RecurringTask, Task, Week
from app.services import (
    habit_row,
    habit_rows,
    log_habit,
    seed_default_habits,
    set_habit_minutes,
    WEEKDAY_LETTERS,
    carry_over,
    create_rule,
    delete_rule,
    describe_weekdays,
    today,
    get_or_create_week,
    parse_quick_time,
    sort_tasks,
    week_days,
    week_performance,
)

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=BASE / "templates")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with Session(_db.engine) as session:
        seed_default_habits(session)
    yield


app = FastAPI(title="Weekforge", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/", response_class=RedirectResponse)
def index():
    return RedirectResponse(f"/week/{today().isoformat()}")


@app.get("/week/{day}", response_class=HTMLResponse)
def week_view(request: Request, day: date, session: Session = Depends(get_session)):
    week = get_or_create_week(session, day)
    tasks = session.exec(select(Task).where(Task.week_id == week.id)).all()
    by_day = {d: sort_tasks([t for t in tasks if t.day == d]) for _, d in week_days(week)}
    backlog = [t for t in tasks if t.day is None]
    return templates.TemplateResponse(
        request,
        "week.html",
        {
            "week": week,
            "days": week_days(week),
            "by_day": by_day,
            "backlog": backlog,
            "perf": week_performance(session, week),
            "habit_rows": habit_rows(session, week),
            "prev_week": week.start_date - timedelta(days=7),
            "next_week": week.start_date + timedelta(days=7),
        },
    )


@app.post("/week/{week_id}/focus", response_class=HTMLResponse)
def set_focus(week_id: int, focus_word: str = Form(""), session: Session = Depends(get_session)):
    week = session.get(Week, week_id)
    if week is None:
        raise HTTPException(404)
    week.focus_word = focus_word.strip()
    session.add(week)
    session.commit()
    return HTMLResponse("")


_WEEK_TEXT_FIELDS = ("notes", "reminders")
_WEEK_TEXT_MAX = 10_000


@app.post("/week/{week_id}/text", response_class=HTMLResponse)
async def save_week_text(request: Request, week_id: int, session: Session = Depends(get_session)):
    """Autosave for the week's notes / reminders. Only fields present in the form change,
    and "" clears a field (so the raw form is read instead of Form())."""
    form = await request.form()
    week = session.get(Week, week_id)
    if week is None:
        raise HTTPException(404)
    fields = [f for f in _WEEK_TEXT_FIELDS if f in form]
    if not fields:
        raise HTTPException(422, "Nothing to save")
    for field in fields:
        value = str(form[field])
        if len(value) > _WEEK_TEXT_MAX:
            raise HTTPException(422, "Text too long")
        setattr(week, field, value.rstrip())
    session.add(week)
    session.commit()
    return HTMLResponse(f"Salvo às {datetime.now().strftime('%H:%M')}")


@app.post("/week/{week_id}/carry-over", response_class=HTMLResponse)
def carry_over_week(week_id: int, session: Session = Depends(get_session)):
    week = session.get(Week, week_id)
    if week is None:
        raise HTTPException(404)
    next_week, _ = carry_over(session, week)
    # Open the next week, where the carried tasks wait in the to-do list.
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = f"/week/{next_week.start_date.isoformat()}"
    return response


@app.post("/week/{week_id}/tasks", response_class=HTMLResponse)
def add_task(
    request: Request,
    week_id: int,
    title: str = Form(...),
    day: Optional[date] = Form(None),
    session: Session = Depends(get_session),
):
    if session.get(Week, week_id) is None:
        raise HTTPException(404)
    due_time, clean_title = parse_quick_time(title)
    if not clean_title:
        raise HTTPException(422, "Title cannot be empty")
    task = Task(week_id=week_id, title=clean_title, day=day, due_time=due_time)
    session.add(task)
    session.commit()
    session.refresh(task)
    if task.day is None:
        return _task_response(request, session, task)  # row + refreshed performance
    return _changed_response(request, session, task)


def _get_task(session: Session, task_id: int) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(404)
    return task


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_row(request: Request, task_id: int, session: Session = Depends(get_session)):
    """The plain task row (used to cancel an edit)."""
    task = _get_task(session, task_id)
    return templates.TemplateResponse(request, "partials/task.html", {"task": task})


@app.get("/tasks/{task_id}/edit", response_class=HTMLResponse)
def edit_task_form(request: Request, task_id: int, session: Session = Depends(get_session)):
    task = _get_task(session, task_id)
    week = session.get(Week, task.week_id)
    return templates.TemplateResponse(
        request, "partials/task_edit.html", {"task": task, "days": week_days(week)}
    )


def _parse_day(raw: str, week: Week) -> Optional[date]:
    """'' means backlog; otherwise an ISO date that must fall inside the task's week."""
    if raw == "":
        return None
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(422, "Invalid day")
    if not week.start_date <= d < week.start_date + timedelta(days=7):
        raise HTTPException(422, "Day is outside this week")
    return d


def _parse_time(raw: str) -> Optional[time]:
    """'' clears the time; otherwise HH:MM."""
    if raw == "":
        return None
    try:
        return time.fromisoformat(raw)
    except ValueError:
        raise HTTPException(422, "Invalid time")


def _day_tasks(session: Session, week_id: int, d: date) -> list[Task]:
    return sort_tasks(session.exec(select(Task).where(Task.week_id == week_id, Task.day == d)).all())


_ORIGIN_NONE = object()  # task is new: nothing to remove


def _changed_response(
    request: Request, session: Session, task: Task, origin=_ORIGIN_NONE
) -> HTMLResponse:
    """After a task is created/edited/moved, re-render where it was and where it is now.

    `origin` is the task's previous day (None = it was in the to-do list). Everything
    is sent as out-of-band swaps and `HX-Reswap: none` skips the main swap, so the
    element that triggered the request may be safely replaced by a re-rendered list.
    """
    week = session.get(Week, task.week_id)
    ctx = {"task": task, "perf": week_performance(session, week)}
    if origin is not _ORIGIN_NONE and origin != task.day:
        if origin is None:
            ctx["remove_from_backlog"] = True
        else:
            ctx["old_d"], ctx["old_day_tasks"] = origin, _day_tasks(session, week.id, origin)
    if task.day is not None:
        ctx["new_day_tasks"] = _day_tasks(session, week.id, task.day)
    response = templates.TemplateResponse(request, "partials/task_changed.html", ctx)
    response.headers["HX-Reswap"] = "none"
    return response


@app.put("/tasks/{task_id}", response_class=HTMLResponse)
async def update_task(request: Request, task_id: int, session: Session = Depends(get_session)):
    # Read the raw form: FastAPI's Form() turns "" into the default value, but here
    # "" is meaningful (day "" = move to to-do, due_time "" = clear the time) and
    # a missing field means "keep as is".
    form = await request.form()
    task = _get_task(session, task_id)
    title = str(form.get("title", "")).strip()
    if not title:
        raise HTTPException(422, "Title cannot be empty")
    old_day = task.day
    task.title = title
    if "day" in form:
        task.day = _parse_day(str(form["day"]), session.get(Week, task.week_id))
    if "due_time" in form:
        task.due_time = _parse_time(str(form["due_time"]))
    session.add(task)
    session.commit()
    session.refresh(task)
    if task.day is None and old_day is None:
        # stayed in the to-do list: just swap the row
        return templates.TemplateResponse(request, "partials/task.html", {"task": task})
    return _changed_response(request, session, task, origin=old_day)


@app.post("/tasks/{task_id}/move", response_class=HTMLResponse)
def move_task(
    request: Request,
    task_id: int,
    day: str = Form(""),
    session: Session = Depends(get_session),
):
    task = _get_task(session, task_id)
    new_day = _parse_day(day, session.get(Week, task.week_id))
    if new_day == task.day:
        return templates.TemplateResponse(request, "partials/task.html", {"task": task})
    old_day, task.day = task.day, new_day
    session.add(task)
    session.commit()
    session.refresh(task)
    return _changed_response(request, session, task, origin=old_day)


@app.delete("/tasks/{task_id}", response_class=HTMLResponse)
def delete_task(request: Request, task_id: int, session: Session = Depends(get_session)):
    task = _get_task(session, task_id)
    week = session.get(Week, task.week_id)
    session.delete(task)
    session.commit()
    # Empty main body removes the row (hx-swap="outerHTML"); the performance box is
    # refreshed out-of-band (score and the carry-over counter).
    return templates.TemplateResponse(
        request,
        "partials/performance.html",
        {"perf": week_performance(session, week), "oob": True},
    )


@app.post("/tasks/{task_id}/toggle", response_class=HTMLResponse)
def toggle_task(request: Request, task_id: int, session: Session = Depends(get_session)):
    task = _get_task(session, task_id)
    task.done = not task.done
    session.add(task)
    session.commit()
    session.refresh(task)
    return _task_response(request, session, task)


def _task_response(request: Request, session: Session, task: Task) -> HTMLResponse:
    """Render the task row plus an out-of-band update of the performance box."""
    week = session.get(Week, task.week_id)
    return templates.TemplateResponse(
        request,
        "partials/task_oob.html",
        {"task": task, "perf": week_performance(session, week)},
    )


# --- recurring tasks ------------------------------------------------------------


def _recurring_page(request: Request, session: Session, error: str = "", status_code: int = 200):
    rules = session.exec(select(RecurringTask).order_by(RecurringTask.id)).all()
    return templates.TemplateResponse(
        request,
        "recurring.html",
        {
            "rules": rules,
            "letters": WEEKDAY_LETTERS,
            "describe": describe_weekdays,
            "error": error,
            "this_week": today().isoformat(),
        },
        status_code=status_code,
    )


@app.get("/recurring", response_class=HTMLResponse)
def recurring_list(request: Request, session: Session = Depends(get_session)):
    return _recurring_page(request, session)


@app.post("/recurring", response_class=HTMLResponse)
async def recurring_create(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    title = str(form.get("title", "")).strip()
    try:
        weekdays = sorted({int(v) for v in form.getlist("weekdays")})
    except ValueError:
        weekdays = []
    if not title or not weekdays or any(not 0 <= d <= 6 for d in weekdays):
        return _recurring_page(
            request, session, error="Informe um título e pelo menos um dia.", status_code=422
        )
    create_rule(session, title, weekdays)
    return RedirectResponse("/recurring", status_code=303)


@app.post("/recurring/{rule_id}/delete", response_class=HTMLResponse)
def recurring_delete(rule_id: int, session: Session = Depends(get_session)):
    rule = session.get(RecurringTask, rule_id)
    if rule is None:
        raise HTTPException(404)
    delete_rule(session, rule)
    return RedirectResponse("/recurring", status_code=303)


# --- habits ---------------------------------------------------------------------


def _get_habit(session: Session, habit_id: int) -> Habit:
    habit = session.get(Habit, habit_id)
    if habit is None:
        raise HTTPException(404)
    return habit


@app.post("/habits/{habit_id}/log", response_class=HTMLResponse)
def habit_log(
    request: Request,
    habit_id: int,
    day: date = Form(...),
    action: str = Form(...),
    session: Session = Depends(get_session),
):
    habit = _get_habit(session, habit_id)
    allowed = {"toggle"} if habit.kind == HabitKind.check else {"inc", "dec"}
    if action not in allowed:
        raise HTTPException(422, "Invalid action for this habit")
    if day > today():
        raise HTTPException(422, "Cannot log a future day")
    log_habit(session, habit, day, action)
    week = get_or_create_week(session, day)
    return templates.TemplateResponse(
        request, "partials/habit_row.html", {"row": habit_row(session, habit, week)}
    )


@app.post("/habits/{habit_id}/minutes", response_class=HTMLResponse)
def habit_minutes(
    habit_id: int,
    week_id: int = Form(...),
    minutes: str = Form("0"),
    session: Session = Depends(get_session),
):
    habit = _get_habit(session, habit_id)
    week = session.get(Week, week_id)
    if week is None:
        raise HTTPException(404)
    try:
        value = int(minutes or 0)
    except ValueError:
        raise HTTPException(422, "Minutes must be a number")
    if not 0 <= value <= 7 * 24 * 60:
        raise HTTPException(422, "Minutes out of range")
    set_habit_minutes(session, habit, week, value)
    return HTMLResponse("✓")


def _habits_page(request: Request, session: Session, error: str = "", status_code: int = 200):
    habits = session.exec(select(Habit).order_by(Habit.active.desc(), Habit.id)).all()
    return templates.TemplateResponse(
        request,
        "habits.html",
        {"habits": habits, "error": error, "this_week": today().isoformat()},
        status_code=status_code,
    )


def _habit_fields(form) -> tuple[str, str, int]:
    name = str(form.get("name", "")).strip()
    emoji = str(form.get("emoji", "")).strip()[:4]
    try:
        target = int(form.get("daily_target") or 1)
    except ValueError:
        target = 0
    if not name or len(name) > 60 or not 1 <= target <= 99:
        raise ValueError("Nome (até 60 caracteres) e meta entre 1 e 99.")
    return name, emoji, target


@app.get("/habits", response_class=HTMLResponse)
def habits_list(request: Request, session: Session = Depends(get_session)):
    return _habits_page(request, session)


@app.post("/habits", response_class=HTMLResponse)
async def habits_create(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    try:
        name, emoji, target = _habit_fields(form)
        kind = HabitKind(str(form.get("kind", "check")))
    except ValueError as e:
        msg = str(e) if "Nome" in str(e) else "Tipo inválido."
        return _habits_page(request, session, error=msg, status_code=422)
    session.add(Habit(name=name, emoji=emoji, kind=kind,
                      daily_target=target if kind == HabitKind.counter else 1))
    session.commit()
    return RedirectResponse("/habits", status_code=303)


@app.post("/habits/{habit_id}", response_class=HTMLResponse)
async def habits_update(request: Request, habit_id: int, session: Session = Depends(get_session)):
    habit = _get_habit(session, habit_id)
    form = await request.form()
    try:
        habit.name, habit.emoji, target = _habit_fields(form)
    except ValueError as e:
        session.rollback()
        return _habits_page(request, session, error=str(e), status_code=422)
    if habit.kind == HabitKind.counter:
        habit.daily_target = target
    session.add(habit)
    session.commit()
    return RedirectResponse("/habits", status_code=303)


@app.post("/habits/{habit_id}/archive", response_class=HTMLResponse)
def habits_archive(habit_id: int, session: Session = Depends(get_session)):
    """Toggle archived/active. Archived habits leave the grid but keep their history."""
    habit = _get_habit(session, habit_id)
    habit.active = not habit.active
    session.add(habit)
    session.commit()
    return RedirectResponse("/habits", status_code=303)
