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
    assert 'id="performance"' not in r.text


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


def test_delete_backlog_task_returns_empty(client):
    client.get("/week/2026-11-01")
    client.post("/week/1/tasks", data={"title": "Comprar caderno"})
    r = client.delete("/tasks/1")
    assert r.status_code == 200 and r.text == ""


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
    assert 'hx-swap-oob="beforeend:#day-2026-11-04"' in r.text
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
    assert 'beforeend:#day-2026-11-07' in r.text
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
    assert 'beforeend:#day-2026-11-05' in r.text and "Treino leve" in r.text


def test_put_without_day_keeps_day(client):
    _week_with_task(client)
    r = client.put("/tasks/1", data={"title": "Treino leve"})
    assert "hx-swap-oob" not in r.text
    page = client.get("/week/2026-11-01").text
    mon = page.split('id="day-2026-11-02"')[1].split("</ul>")[0]
    assert "Treino leve" in mon


def test_page_has_drop_zones_and_draggable_rows(client):
    _week_with_task(client)
    page = client.get("/week/2026-11-01").text
    assert page.count("data-drop-day=") == 8  # 7 days + to-do
    assert 'draggable="true"' in page
    assert "/static/app.js" in page
