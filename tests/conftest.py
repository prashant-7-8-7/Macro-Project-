"""Every test uses a disposable database, never a developer's document library."""
import pytest


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    import src.database.db as database
    from src.database.repository import DocumentRepository
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    DocumentRepository._migrated = False
    database.init_db()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from src.api.routes import app
    with TestClient(app) as session:
        yield session
    app.dependency_overrides.clear()
