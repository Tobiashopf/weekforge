# Weekforge

A self-hosted weekly planner for people who plan their week by hand and want the same flow digitally, plus the numbers paper can't give: completion rates, habit streaks and reminders.

Weekforge started as a replacement for my own paper weekly planner. It keeps the parts that work on paper (a focus word for the week, a short task list per day, a habit grid and a weekly score) and adds metrics, history and notifications.

**Who it's for:** individuals who want a simple, private planner they run themselves. It is single-user and self-hosted by design: your data stays in a SQLite file on your machine.

## Features

**Plan the week**
- Week view (Sunday to Saturday) with a focus word, tasks per day and navigation between weeks
- Quick entry with a time: typing `14h Meeting` or `9:30 Doctor` sets the time; timed tasks are sorted first
- Edit, delete and move tasks between days or to the to-do list (drag and drop, or from the edit form on mobile)
- Recurring tasks: weekly rules (e.g. Mon/Wed/Fri at 7:00) filled into the current and every new week
- Carry unfinished tasks over to next week's to-do, without hiding them from this week's score
- Week reminders and notes, saved automatically as you type

**Track habits**
- Weekly habit grid like a paper planner: check habits with weekly minutes, counter habits (glasses of water) with a daily target
- Default habits on first run; rename, re-target, add or archive (history is kept)

**See how it's going**
- Live weekly performance: done vs. pending tasks
- Metrics page: completion per week (4 to 52 weeks) and per weekday, habit streaks and records, a year heatmap; every chart has a hover/keyboard tooltip and a table view
- Export: tasks and habits as CSV (safe against spreadsheet formula injection), full backup as JSON

**Notifications**
- Installable as an app (PWA); Web Push to each device you enable, with keys generated on first run

**Planned** (about 34 hours, see [ROADMAP.md](ROADMAP.md))
- Reminders: tasks at their time, habits still open in the evening, water, Sunday planning, quiet hours
- Gamification: weekly targets per habit, XP per week (100 for a perfect week), levels, achievements, streak protection
- History: best weeks of the year, a progress page, habit strength
- Focus timer that feeds habit minutes, a guided weekly review
- Offline mode, Docker, Alembic migrations, restore from backup

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

With the server running, open `http://localhost:8000` in your browser (it is served by your own computer, so the address only works while `uvicorn` is running). The database file `weekforge.db` is created on first run.

Run the tests:

```bash
pytest
```

## Project structure

```
app/
  main.py        routes (FastAPI + HTMX partials)
  models.py      Week, Task, RecurringTask, Habit, HabitLog, HabitWeek
  services.py    weeks, tasks, carry-over, recurring rules, habits
  metrics.py     numbers for the metrics page (read-only)
  export.py      CSV and JSON export (read-only)
  db.py          engine, sessions and small startup migrations
  templates/     Jinja2 pages, partials and server-rendered SVG charts
  static/        CSS and a little JavaScript (drag and drop, chart tooltips)
tests/           pytest suite
```

## License

[MIT](LICENSE) © 2026 Tobias Hopf
