import os
import tempfile

# Тесты работают с отдельным временным файлом БД
os.environ["CATALOG_DB"] = os.path.join(tempfile.mkdtemp(), "test_catalog.db")

import pytest  # noqa: E402

from app.seed import reset_database  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    reset_database()
    yield
