import os

# Тесты работают с отдельной базой, чтобы не трогать основную
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/marketplace_test"
)

import pytest  # noqa: E402

from app.seed import reset_database  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    reset_database()
    yield
