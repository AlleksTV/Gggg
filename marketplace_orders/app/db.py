"""Подключение к PostgreSQL."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/marketplace",
)

# pool_size побольше, чтобы демонстрация гонки могла открыть много соединений сразу
engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=20)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
