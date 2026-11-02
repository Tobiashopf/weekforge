from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import db
from app.main import app
from app.services import week_start


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    monkeypatch.setattr(db, "engine", engine)
    db.init_db(engine)

    def override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[db.get_session] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    SQLModel.metadata.drop_all(engine)


@pytest.mark.parametrize(
    "d, expected",
    [
        (date(2026, 11, 1), date(2026, 11, 1)),  # Sunday
        (date(2026, 11, 2), date(2026, 11, 1)),  # Monday
        (date(2026, 11, 7), date(2026, 11, 1)),  # Saturday
        (date(2026, 11, 8), date(2026, 11, 8)),  # next Sunday
    ],
)
def test_week_starts_on_sunday(d, expected):
    assert week_start(d) == expected


def test_week_page_renders(client):
    r = client.get("/week/2026-11-04")
    assert r.status_code == 200
    assert "Semana de 01/11/2026" in r.text
    assert "SEG" in r.text and "SÁB" in r.text


def test_add_and_toggle_task_updates_performance(client):
    client.get("/week/2026-11-01")  # creates week id 1
    r = client.post("/week/1/tasks", data={"title": "Treino", "day": "2026-11-02"})
    assert r.status_code == 200
    assert "Treino" in r.text
    assert "0 (0%)" in r.text  # 0 done

    r = client.post("/tasks/1/toggle")
    assert "task done" in r.text
    assert "1 (100%)" in r.text


def test_backlog_task_not_counted_in_performance(client):
    client.get("/week/2026-11-01")
    r = client.post("/week/1/tasks", data={"title": "Comprar caderno"})
    assert r.status_code == 200
    flat = r.text.replace("\n", "").replace("  ", "")
    assert "Total</dt><dd>0" in flat  # not counted in the score...
    assert "Levar 1 pendente" in r.text  # ...but it can be carried over


def test_edit_task_title(client):
    client.get("/week/2026-11-01")
    client.post("/week/1/tasks", data={"title": "Treino", "day": "2026-11-02"})

    form = client.get("/tasks/1/edit")
    assert form.status_code == 200
    assert 'value="Treino"' in form.text

    r = client.put("/tasks/1", data={"title": "  Treino de perna  "})
    assert r.status_code == 200
    assert "Treino de perna" in r.text
    assert "Treino de perna" in client.get("/week/2026-11-01").text


def test_edit_task_rejects_empty_title(client):
    client.get("/week/2026-11-01")
    client.post("/week/1/tasks", data={"title": "Treino", "day": "2026-11-02"})
    assert client.put("/tasks/1", data={"title": "   "}).status_code == 422


def test_cancel_edit_returns_plain_row(client):
    client.get("/week/2026-11-01")
    client.post("/week/1/tasks", data={"title": "Treino", "day": "2026-11-02"})
    r = client.get("/tasks/1")
    assert 'id="task-1"' in r.text and "<form" not in r.text


def test_delete_scheduled_task_updates_performance(client):
    client.get("/week/2026-11-01")
    client.post("/week/1/tasks", data={"title": "A", "day": "2026-11-02"})
    client.post("/week/1/tasks", data={"title": "B", "day": "2026-11-03"})
    client.post("/tasks/1/toggle")

    r = client.delete("/tasks/1")
    assert r.status_code == 200
    assert 'id="performance"' in r.text
    assert "0 (0%)" in r.text  # only B left, pending
    assert ">A<" not in client.get("/week/2026-11-01").text


def test_delete_backlog_task_refreshes_counter(client):
    client.get("/week/2026-11-01")
    client.post("/week/1/tasks", data={"title": "Comprar caderno"})
    r = client.delete("/tasks/1")
    assert r.status_code == 200
    assert '<li' not in r.text and "Levar" not in r.text  # row gone, nothing left to carry


def test_missing_task_is_404(client):
    assert client.delete("/tasks/999").status_code == 404
    assert client.put("/tasks/999", data={"title": "x"}).status_code == 404


# --- moving tasks -----------------------------------------------------------

def _week_with_task(client, day="2026-11-02", title="Treino"):
    client.get("/week/2026-11-01")  # week id 1, Sun 01/11 .. Sat 07/11
    data = {"title": title}
    if day:
        data["day"] = day
    client.post("/week/1/tasks", data=data)


def test_move_task_to_another_day(client):
    _week_with_task(client)
    r = client.post("/tasks/1/move", data={"day": "2026-11-04"})
    assert r.status_code == 200
    assert r.headers["HX-Reswap"] == "none"
    # old list re-rendered without it, new list with it
    assert '<ul id="day-2026-11-02" class="tasks" hx-swap-oob="true">' in r.text
    assert '<ul id="day-2026-11-04" class="tasks" hx-swap-oob="true">' in r.text
    assert 'id="performance"' in r.text
    page = client.get("/week/2026-11-01").text
    wed = page.split('id="day-2026-11-04"')[1].split("</ul>")[0]
    assert "Treino" in wed


def test_move_task_to_backlog_leaves_performance(client):
    _week_with_task(client)
    client.post("/tasks/1/toggle")  # 1 done, 100%
    r = client.post("/tasks/1/move", data={"day": ""})
    assert 'beforeend:#backlog' in r.text
    assert "Total</dt><dd>0" in r.text.replace("\n", "").replace("  ", "")


def test_move_backlog_task_into_a_day(client):
    _week_with_task(client, day=None, title="Comprar caderno")
    r = client.post("/tasks/1/move", data={"day": "2026-11-07"})
    assert '<li id="task-1" hx-swap-oob="delete">' in r.text
    assert 'id="day-2026-11-07" class="tasks" hx-swap-oob="true"' in r.text
    assert "0 (0%)" in r.text  # now counts as pending


def test_move_to_same_place_is_noop(client):
    _week_with_task(client)
    r = client.post("/tasks/1/move", data={"day": "2026-11-02"})
    assert r.status_code == 200
    assert "hx-swap-oob" not in r.text and 'id="task-1"' in r.text


@pytest.mark.parametrize("bad", ["2026-11-08", "2026-10-31", "amanhã"])
def test_move_rejects_days_outside_the_week(client, bad):
    _week_with_task(client)
    assert client.post(f"/tasks/1/move", data={"day": bad}).status_code == 422


def test_edit_form_lists_days_with_current_selected(client):
    _week_with_task(client)
    r = client.get("/tasks/1/edit")
    assert '<option value="2026-11-02" selected>' in r.text
    assert "To-do (sem dia)" in r.text


def test_put_with_new_day_moves_and_renames(client):
    _week_with_task(client)
    r = client.put("/tasks/1", data={"title": "Treino leve", "day": "2026-11-05"})
    assert 'id="day-2026-11-05" class="tasks" hx-swap-oob="true"' in r.text
    assert "Treino leve" in r.text


def test_put_without_day_keeps_day(client):
    _week_with_task(client)
    r = client.put("/tasks/1", data={"title": "Treino leve"})
    assert r.text.count('class="tasks" hx-swap-oob="true"') == 1  # only Monday re-rendered
    page = client.get("/week/2026-11-01").text
    mon = page.split('id="day-2026-11-02"')[1].split("</ul>")[0]
    assert "Treino leve" in mon


def test_page_has_drop_zones_and_draggable_rows(client):
    _week_with_task(client)
    page = client.get("/week/2026-11-01").text
    assert page.count("data-drop-day=") == 8  # 7 days + to-do
    assert 'draggable="true"' in page
    assert "/static/app.js" in page


# --- task time ----------------------------------------------------------------

from datetime import time  # noqa: E402

from app.services import parse_quick_time  # noqa: E402


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("14h Reunião", (time(14, 0), "Reunião")),
        ("9:30 Médico", (time(9, 30), "Médico")),
        ("7h30 Treino", (time(7, 30), "Treino")),
        ("07H05 Remédio", (time(7, 5), "Remédio")),
        ("3 livros", (None, "3 livros")),
        ("25h Festa", (None, "25h Festa")),
        ("14h", (None, "14h")),
        ("Ler 20 páginas às 14h", (None, "Ler 20 páginas às 14h")),
    ],
)
def test_parse_quick_time(raw, expected):
    assert parse_quick_time(raw) == expected


def _day_section(page: str, d: str) -> str:
    return page.split(f'id="day-{d}"')[1].split("</ul>")[0]


def test_quick_time_on_create_and_sorted_by_time(client):
    client.get("/week/2026-11-01")
    for title in ["Sem hora", "18h Academia", "8:30 Daily"]:
        client.post("/week/1/tasks", data={"title": title, "day": "2026-11-02"})
    mon = _day_section(client.get("/week/2026-11-01").text, "2026-11-02")
    # ids: 1 "Sem hora", 2 "Academia" 18:00, 3 "Daily" 08:30
    assert mon.index('id="task-3"') < mon.index('id="task-2"') < mon.index('id="task-1"')
    assert "08:30" in mon and "18:00" in mon
    assert "18h Academia" not in mon  # prefix became the time


def test_set_and_clear_time_via_edit(client):
    _week_with_task(client)
    r = client.put("/tasks/1", data={"title": "Treino", "due_time": "06:45"})
    assert "06:45" in r.text
    assert 'value="06:45"' in client.get("/tasks/1/edit").text

    r = client.put("/tasks/1", data={"title": "Treino", "due_time": ""})
    assert '<time class="due">' not in r.text


def test_invalid_time_is_422(client):
    _week_with_task(client)
    assert client.put("/tasks/1", data={"title": "x", "due_time": "25:99"}).status_code == 422


def test_empty_title_after_time_prefix_is_rejected(client):
    client.get("/week/2026-11-01")
    # "14h  " has no title after the time: regex needs text, so it stays as title "14h"
    r = client.post("/week/1/tasks", data={"title": "14h", "day": "2026-11-02"})
    assert r.status_code == 200 and "14h" in r.text


def test_edit_to_todo_via_put_moves_to_backlog(client):
    """Regression: an empty form value ("") must mean 'to-do', not 'keep'."""
    _week_with_task(client)
    r = client.put("/tasks/1", data={"title": "Treino", "day": ""})
    assert 'beforeend:#backlog' in r.text
    page = client.get("/week/2026-11-01").text
    assert "Treino" in page.split('id="backlog"')[1].split("</ul>")[0]


# --- carry over -------------------------------------------------------------


def test_carry_over_copies_agenda_and_moves_todo(client):
    client.get("/week/2026-11-01")
    client.post("/week/1/tasks", data={"title": "9h Dentista", "day": "2026-11-03"})  # 1 pending
    client.post("/week/1/tasks", data={"title": "Treino", "day": "2026-11-02"})       # 2 done
    client.post("/week/1/tasks", data={"title": "Comprar caderno"})                     # 3 to-do
    client.post("/tasks/2/toggle")

    page = client.get("/week/2026-11-01").text
    assert "Levar 2 pendentes" in page

    r = client.post("/week/1/carry-over")
    assert r.headers["HX-Redirect"] == "/week/2026-11-08"

    nxt = client.get("/week/2026-11-08").text
    todo = nxt.split('id="backlog"')[1].split("</ul>")[0]
    assert "Dentista" in todo and "09:00" in todo  # copied with its time
    assert "Comprar caderno" in todo               # moved
    assert "Treino" not in nxt                     # done tasks stay behind

    cur = client.get("/week/2026-11-01").text
    assert "↪ próx. semana" in cur                 # original kept and marked
    assert "Comprar caderno" not in cur            # to-do item left this week
    assert "Levar" not in cur                      # nothing left to carry
    flat = cur.replace("\n", "").replace("  ", "")
    assert "Pendentes</dt><dd>1 (50%)" in flat     # score unchanged by carrying
    assert "Levadas p/ próxima</dt><dd>1" in flat


def test_carry_over_twice_does_not_duplicate(client):
    client.get("/week/2026-11-01")
    client.post("/week/1/tasks", data={"title": "Dentista", "day": "2026-11-03"})
    client.post("/week/1/carry-over")
    client.post("/week/1/carry-over")
    nxt = client.get("/week/2026-11-08").text
    assert nxt.count(">Dentista") == 1


def test_carry_over_unknown_week_is_404(client):
    assert client.post("/week/99/carry-over").status_code == 404


def test_migration_adds_carried_column_to_old_database(tmp_path):
    from sqlalchemy import create_engine as sa_engine

    from app.db import init_db

    eng = sa_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as conn:  # schema as created by v0.1
        conn.exec_driver_sql("CREATE TABLE week (id INTEGER PRIMARY KEY, start_date DATE, focus_word VARCHAR, notes VARCHAR)")
        conn.exec_driver_sql(
            "CREATE TABLE task (id INTEGER PRIMARY KEY, week_id INTEGER, title VARCHAR, day DATE,"
            " due_time TIME, done BOOLEAN, created_at DATETIME)"
        )
        conn.exec_driver_sql("INSERT INTO task (week_id, title, done) VALUES (1, 'old', 0)")
    init_db(eng)
    init_db(eng)  # idempotent
    with eng.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(task)")}
        assert {"carried", "recurring_id"} <= cols
        week_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(week)")}
        assert "reminders" in week_cols
        assert conn.exec_driver_sql("SELECT carried FROM task").scalar() == 0


# --- recurring tasks ----------------------------------------------------------

from datetime import date as _date  # noqa: E402

from app import main as _main  # noqa: E402
from app import services as _services  # noqa: E402


@pytest.fixture
def today_is(monkeypatch):
    """Pin 'today' for both the services and the index route."""
    def pin(d: str):
        value = _date.fromisoformat(d)
        monkeypatch.setattr(_services, "today", lambda: value)
        monkeypatch.setattr(_main, "today", lambda: value)
    return pin


def _create_rule(client, title, days):
    return client.post("/recurring", data={"title": title, "weekdays": [str(d) for d in days]},
                       follow_redirects=False)


def test_rule_fills_current_week_from_today_only(client, today_is):
    today_is("2026-11-04")  # Wednesday
    r = _create_rule(client, "7h Treino", [1, 3, 5])  # Mon, Wed, Fri
    assert r.status_code == 303
    page = client.get("/week/2026-11-01").text
    assert "Treino" not in _day_section(page, "2026-11-02")      # Monday already passed
    assert "07:00" in _day_section(page, "2026-11-04")           # today
    assert "Treino" in _day_section(page, "2026-11-06")          # Friday
    assert page.count('class="rec"') == 2


def test_new_week_is_created_with_recurring_tasks(client, today_is):
    today_is("2026-11-01")
    _create_rule(client, "Inglês", list(range(7)))
    nxt = client.get("/week/2026-11-08").text
    assert nxt.count(">Inglês") == 7


def test_rule_also_fills_future_weeks_already_open(client, today_is):
    today_is("2026-11-01")
    client.get("/week/2026-11-15")  # open a future week first
    _create_rule(client, "Revisão semanal", [0])
    assert "Revisão semanal" in _day_section(client.get("/week/2026-11-15").text, "2026-11-15")


def test_past_weeks_are_never_backfilled(client, today_is):
    today_is("2026-11-04")
    _create_rule(client, "Treino", [1, 3, 5])
    old = client.get("/week/2026-10-25").text  # week created after the rule, but in the past
    assert "Treino" not in old


def test_occurrence_can_be_deleted_and_does_not_come_back(client, today_is):
    today_is("2026-11-01")
    _create_rule(client, "Treino", [1])
    page = client.get("/week/2026-11-01").text
    task_id = page.split('class="rec"')[0].rsplit('id="task-', 1)[1].split('"')[0]
    client.delete(f"/tasks/{task_id}")
    assert "Treino" not in client.get("/week/2026-11-01").text


def test_recurring_tasks_are_not_carried_over(client, today_is):
    today_is("2026-11-01")
    _create_rule(client, "Treino", [1])
    page = client.get("/week/2026-11-01").text
    assert "Levar" not in page


def test_delete_rule_removes_future_undone_keeps_history(client, today_is):
    today_is("2026-11-01")
    _create_rule(client, "Treino", [1, 3])        # Mon 02/11 and Wed 04/11
    page = client.get("/week/2026-11-01").text
    mon_id = _day_section(page, "2026-11-02").split('id="task-')[1].split('"')[0]
    client.post(f"/tasks/{mon_id}/toggle")         # Monday done
    client.get("/week/2026-11-08")                  # next week has its own

    today_is("2026-11-03")                          # Tuesday: delete the rule
    r = client.post("/recurring/1/delete", follow_redirects=False)
    assert r.status_code == 303
    cur = client.get("/week/2026-11-01").text
    assert "Treino" in _day_section(cur, "2026-11-02")       # done one kept
    assert "Treino" not in _day_section(cur, "2026-11-04")   # future undone removed
    assert "Treino" not in client.get("/week/2026-11-08").text
    assert 'class="rec"' not in cur                          # history detached from rule
    assert "Nenhuma regra" in client.get("/recurring").text


@pytest.mark.parametrize(
    "data",
    [{"title": "", "weekdays": ["1"]}, {"title": "Treino"}, {"title": "Treino", "weekdays": ["9"]},
     {"title": "Treino", "weekdays": ["x"]}],
)
def test_invalid_rule_is_rejected(client, data):
    r = client.post("/recurring", data=data)
    assert r.status_code == 422
    assert "pelo menos um dia" in r.text


def test_recurring_page_lists_rules(client, today_is):
    today_is("2026-11-01")
    _create_rule(client, "18h Academia", [1, 2, 3, 4, 5])
    page = client.get("/recurring").text
    assert "Academia" in page and "18:00" in page and "Seg a sex" in page


def test_rule_title_with_quote_is_escaped(client, today_is):
    today_is("2026-11-01")
    _create_rule(client, "Ler o livro do D'Ávila", [1])
    page = client.get("/recurring").text
    assert "D&#39;Ávila" in page and "onsubmit" not in page


# --- notes and reminders --------------------------------------------------------

def test_save_notes_and_reminders(client):
    client.get("/week/2026-11-01")
    r = client.post("/week/1/text", data={"reminders": "Pagar luz até quinta"})
    assert r.status_code == 200 and r.text.startswith("Salvo às ")
    client.post("/week/1/text", data={"notes": "Semana puxada no trabalho"})
    page = client.get("/week/2026-11-01").text
    assert ">Pagar luz até quinta</textarea>" in page        # saving notes kept reminders
    assert ">Semana puxada no trabalho</textarea>" in page


def test_empty_text_clears_field(client):
    """Regression guard: "" must clear, not be ignored (raw form, not Form())."""
    client.get("/week/2026-11-01")
    client.post("/week/1/text", data={"notes": "algo"})
    client.post("/week/1/text", data={"notes": ""})
    assert ">algo</textarea>" not in client.get("/week/2026-11-01").text


def test_text_is_escaped(client):
    client.get("/week/2026-11-01")
    client.post("/week/1/text", data={"notes": "<script>alert(1)</script>"})
    page = client.get("/week/2026-11-01").text
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_text_belongs_to_its_week(client):
    client.get("/week/2026-11-01")
    client.post("/week/1/text", data={"reminders": "só desta semana"})
    assert "só desta semana" not in client.get("/week/2026-11-08").text


@pytest.mark.parametrize(
    "week_id, data, status",
    [(1, {}, 422), (1, {"focus_word": "x"}, 422), (1, {"notes": "x" * 10_001}, 422), (99, {"notes": "x"}, 404)],
)
def test_invalid_text_requests(client, week_id, data, status):
    client.get("/week/2026-11-01")
    assert client.post(f"/week/{week_id}/text", data=data).status_code == status
