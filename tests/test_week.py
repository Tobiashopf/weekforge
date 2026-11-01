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
