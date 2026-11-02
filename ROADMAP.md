# Roadmap

Weekforge is a planner I use myself, so the order below follows what I miss most while
using it. Estimates are rough and only meant to size the work.

**Remaining work: about 34 hours** (v0.5 to v0.9).

## Done

### v0.1 — Week agenda
- [x] Week model starting on Sunday, navigation between weeks
- [x] Tasks per day and unscheduled backlog
- [x] Focus word for the week
- [x] Weekly performance (done / pending / total, %)
- [x] Test suite and CI

### v0.2 — Tasks, complete
- [x] Edit and delete tasks
- [x] Move tasks between days and from the backlog to a day (drag and drop)
- [x] Optional time on a task (quick entry "14h …", sorted by time)
- [x] Carry unfinished tasks over to the next week
- [x] Recurring tasks (every weekday, every Monday…)
- [x] Week notes and weekly reminders fields (autosave)

### v0.3 — Habits
- [x] Habit settings: name, emoji, type (check / counter), daily target, archive
- [x] Habit grid for the week (one cell per day, future days locked)
- [x] Weekly minutes per check habit; +1 / −1 for counters (water)
- [x] Default habit set on first run, fully editable

### v0.4 — Metrics
- [x] Dashboard: completion rate per week over time (4 / 12 / 26 / 52 weeks)
- [x] Completion by weekday (which days slip?)
- [x] Habit streaks and best streak
- [x] Minutes per habit per week; average water per day
- [x] Year heatmap
- [x] CSV / JSON export

## Next

### v0.5 — Notifications and PWA (~6h left)
- [x] Web app manifest and service worker (installable on phone and desktop)
- [x] Web Push with VAPID keys (generated on first use or from `.env`), per-device subscribe and test
- [ ] Scheduler (in-process, survives restarts) for: task reminders at their time, evening "habits still open" nudge, water reminders at an interval, Sunday planning prompt, end-of-week review prompt — 3h
- [ ] Notification settings: which reminders are on, times, quiet hours — 1.5h
- [ ] Offline support for the current week (cache the shell, queue changes made offline) — 1.5h

### v0.6 — Gamification: weekly goals, XP and levels (~8h)
The idea: make personal development more fun and make progress visible.
- [ ] **Weekly target per habit** ("5 of 7 days", "every day"): the grid and summary count against the target, not against 7 — 2h
- [ ] **Healthy eating** habit in the default set (target: 6 of 7 days), and a migration that offers it to existing installs — 0.5h
- [ ] **Weekly XP**: a week that hits every habit target is worth 100 XP; partial weeks earn proportional XP (60% of the targets met → 60 XP). Stored per week so changing targets later doesn't rewrite history — 2h
- [ ] **Levels**: total XP → level with a growing curve; progress bar to the next level on the week page; push notification on level up — 1.5h
- [ ] **Progress page**: level, XP per week chart, XP this month/year, best week — 2h

### v0.7 — History and achievements (~7h)
- [ ] **Best weeks of the year** ("hall of fame"): weeks ranked by habit completion / XP, with the habits that made each one — 2h
- [ ] **Achievements** (badges) with a definition table and tests: first perfect week, 4 perfect weeks in a row, 30 days of water target, 100 meditation sessions, first level 10… — 3h
- [ ] **Streak protection** (inspired by Duolingo's streak freeze): earn a "shield" every 2 perfect weeks; one missed day uses it instead of breaking the streak — 2h

### v0.8 — Ideas from other personal development apps (~7h)
- [ ] **Habit strength** (inspired by Loop Habit Tracker): a score that rises with consistency and decays slowly, so one missed day doesn't erase months — 2h
- [ ] **Focus timer** (inspired by Forest / Pomodoro apps): start a timer from a habit (reading, study, English); finished sessions add to the habit's minutes and mark the day — 3h
- [ ] **Weekly review ritual**: on Sunday, a short guided review (score, what went well, what to change) saved with the week; carry-over offered at the end — 1.5h
- [ ] **Power phrases**: user-written phrases shown on rotation on the week page — 0.5h

### v0.9 — Quality and self-hosting (~6h)
- [ ] Database migrations with Alembic (replace the startup column helper) — 2h
- [ ] Docker image and docker-compose for a home server — 1.5h
- [ ] Restore from the JSON backup — 1.5h
- [ ] Dark/light toggle, keyboard shortcuts, accessibility pass — 1h

## Not planned for now
- **Ranking against other people.** It would need accounts, a central server and storing
  other people's productivity data, which changes what Weekforge is (a private,
  single-user, self-hosted app). For now, comparison is with yourself: best weeks,
  levels and achievements. A privacy-preserving option (e.g. a shareable weekly XP card
  the user chooses to post) may be considered later.

## Inspirations
| App | Idea taken |
|---|---|
| Paper weekly planner (the one I used) | the week layout, habit grid and weekly score |
| Duolingo | streaks, and a way to protect them |
| Loop Habit Tracker | habit strength instead of all-or-nothing streaks |
| Forest / Pomodoro apps | focus sessions that feed the habit's time |
| Habitica, Todoist Karma | XP, levels and achievements for real-life progress |
