"""Weekforge web app."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, time, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.db import get_session, init_db
from app.models import Task, Week
from app.services import (
    carry_over,
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
    yield


app = FastAPI(title="Weekforge", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/", response_class=RedirectResponse)
def index():
    return RedirectResponse(f"/week/{date.today().isoformat()}")


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
