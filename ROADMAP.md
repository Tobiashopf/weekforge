# Roadmap

Estimates are rough and only meant to size the work.

## v0.1 — Week agenda (done)
- [x] Week model starting on Sunday, navigation between weeks
- [x] Tasks per day and unscheduled backlog
- [x] Focus word for the week
- [x] Weekly performance (done / pending / total, %)
- [x] Test suite and CI

## v0.2 — Tasks, complete (~4h)
- [x] Edit and delete tasks
- [ ] Move tasks between days and from the backlog to a day (drag and drop)
- [ ] Optional time on a task
- [ ] Carry unfinished tasks over to the next week
- [ ] Recurring tasks (every weekday, every Monday…)
- [ ] Week notes and weekly reminders fields

## v0.3 — Habits (~5h)
- [ ] Habit settings: name, type (check / counter), daily target, active
- [ ] Habit grid for the week (one cell per day)
- [ ] Minutes per check habit; +1 / −1 for counters (water)
- [ ] Default habit set on first run, fully editable

## v0.4 — Metrics (~5h)
- [ ] Dashboard: completion rate per week over time
- [ ] Completion by weekday (which days slip?)
- [ ] Habit streaks and best streak
- [ ] Minutes per habit per week; average water per day
- [ ] Year heatmap
- [ ] CSV / JSON export

## v0.5 — Notifications and PWA (~6h)
- [ ] Web app manifest and service worker (installable on phone and desktop)
- [ ] Web Push with VAPID keys (keys only in `.env`)
- [ ] Scheduler for: task reminders, evening "habits still open" nudge, water reminders at an interval, Sunday planning prompt, weekly review prompt
- [ ] Notification settings page (quiet hours, which reminders are on)
- [ ] Offline support for the current week

## v0.6 — Weekly review and polish (~4h)
- [ ] Weekly review: score, what went well / what to change
- [ ] Rotating motivational phrases written by the user
- [ ] Dark/light toggle, keyboard shortcuts, accessibility pass
- [ ] Docker image and docker-compose for self-hosting
- [ ] Database migrations (Alembic)

## Later ideas
- [ ] Calendar export (.ics) for timed tasks
- [ ] Simple local backup / restore
- [ ] Optional single-user password for when it runs on a home server
