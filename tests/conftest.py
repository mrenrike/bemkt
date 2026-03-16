import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, get_db
import os

@pytest.fixture(autouse=True)
def test_db(tmp_path, monkeypatch):
    """Banco de dados isolado para cada teste."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    init_db(db_path)
    yield db_path

@pytest.fixture
def client(test_db):
    return TestClient(app)
