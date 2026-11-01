"""Weekforge web app."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.db import get_session, init_db
from app.models import Task, Week
from app.services import get_or_create_week, week_days, week_performance

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
    by_day = {d: [t for t in tasks if t.day == d] for _, d in week_days(week)}
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
    task = Task(week_id=week_id, title=title.strip(), day=day)
    session.add(task)
    session.commit()
    session.refresh(task)
    return _task_response(request, session, task)


@app.post("/tasks/{task_id}/toggle", response_class=HTMLResponse)
def toggle_task(request: Request, task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(404)
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
