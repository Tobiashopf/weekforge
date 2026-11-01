# Weekforge

A self-hosted weekly planner for people who plan their week by hand and want the same flow digitally, plus the numbers paper can't give: completion rates, habit streaks and reminders.

Weekforge started as a replacement for my own paper weekly planner. It keeps the parts that work on paper (a focus word for the week, a short task list per day, a habit grid and a weekly score) and adds metrics, history and notifications.

**Who it's for:** individuals who want a simple, private planner they run themselves. It is single-user and self-hosted by design: your data stays in a SQLite file on your machine.

## Features

**Working now**
- Week view (Sunday to Saturday) with tasks per day and navigation between weeks
- Focus word for the week
- Unscheduled to-do list (backlog)
- Weekly performance: done vs. pending tasks with percentages, updated live

**Planned** (see [ROADMAP.md](ROADMAP.md))
- Habit tracking: check habits with minutes (meditation, reading, exercise, study…) and counters (glasses of water)
- Metrics dashboard: weekly history, streaks, heatmap, minutes per habit
- Push notifications: task reminders, habit nudges, water reminders, Sunday planning and weekly review
- Installable PWA with offline support
- Weekly review, carry-over of unfinished tasks, recurring tasks
- CSV/JSON export

## Built with

- [FastAPI](https://fastapi.tiangolo.com/) and [SQLModel](https://sqlmodel.tiangolo.com/) on SQLite
- [HTMX](https://htmx.org/) with Jinja2 templates: server-rendered, no JavaScript build step
- pytest and GitHub Actions

## Run it locally

Requires Python 3.11+.

```bash
git clone https://github.com/Tobiashopf/weekforge.git
cd weekforge
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env             # optional; defaults work out of the box
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. The database file `weekforge.db` is created on first run.

Run the tests:

```bash
pytest
```

## Project structure

```
app/
  main.py        routes (FastAPI + HTMX partials)
  models.py      Week, Task, Habit, HabitLog
  services.py    week logic and performance metrics
  db.py          engine and sessions
  templates/     Jinja2 pages and partials
  static/        CSS
tests/           pytest suite
```

## License

[MIT](LICENSE) © 2026 Tobias Hopf
