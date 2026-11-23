"""Подключение к SQLite. База - обычный файл catalog.db рядом с проектом."""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_PATH = os.getenv("CATALOG_DB", "catalog.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},  # FastAPI работает в нескольких потоках
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):
    # В SQLite проверка внешних ключей по умолчанию ВЫКЛЮЧЕНА - включаем
    dbapi_conn.execute("PRAGMA foreign_keys = ON")
    # Встроенная lower() в SQLite понимает только латиницу. Регистрируем свою на Python,
    # чтобы запасной поиск через LIKE работал и с русскими буквами.
    dbapi_conn.create_function(
        "py_lower", 1, lambda s: s.lower().replace("ё", "е") if isinstance(s, str) else s,
        deterministic=True
    )


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
