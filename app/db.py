"""Database engine and session helpers."""
import os
from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv("WEEKFORGE_DATABASE_URL", "sqlite:///./weekforge.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


# Columns added after v0.1, applied to existing SQLite databases on startup.
# (table, column, DDL). Replace with Alembic migrations once the schema grows.
_ADDED_COLUMNS = [
    ("task", "carried", "BOOLEAN NOT NULL DEFAULT 0"),
    ("task", "recurring_id", "INTEGER"),
    ("week", "reminders", "VARCHAR NOT NULL DEFAULT ''"),
]


def _add_missing_columns(eng) -> None:
    with eng.begin() as conn:
        for table, column, ddl in _ADDED_COLUMNS:
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if existing and column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db(eng=None) -> None:
    from app import models  # noqa: F401  (registers tables)

    eng = eng or engine
    SQLModel.metadata.create_all(eng)
    _add_missing_columns(eng)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
