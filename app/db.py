"""Database engine and session helpers."""
import os
from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv("WEEKFORGE_DATABASE_URL", "sqlite:///./weekforge.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def init_db(eng=None) -> None:
    from app import models  # noqa: F401  (registers tables)

    SQLModel.metadata.create_all(eng or engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
