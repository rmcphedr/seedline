import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from apps.api.main import app
from backend.db import Base, get_db


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(db_engine, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")

    def session_override():
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_db] = session_override
    with TestClient(app, headers={"X-Admin-Key": "test-admin-key"}) as test_client:
        yield test_client
    app.dependency_overrides.clear()
