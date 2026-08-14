import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import app.database  # Pre-import to resolve patch target properly
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def mock_db():
    """
    Mocked SQLAlchemy Database Session.
    """
    db = MagicMock()
    return db

@pytest.fixture(autouse=True)
def override_db(mock_db):
    """
    Overrides the FastAPI get_db dependency to yield mock_db.
    """
    from app.main import app
    from app.database import get_db
    app.dependency_overrides[get_db] = lambda: mock_db
    yield
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture
def client():
    """
    Test client for FastAPI app.
    """
    with patch("app.database.engine"): # Prevent engine connect attempts on import/run
        from app.main import app
        yield TestClient(app)


@pytest.fixture
def mock_db_connection():
    """
    Fixture to mock DB check in app.database.check_db_connection.
    """
    with patch("app.routers.health.check_db_connection") as mock_check:
        yield mock_check

@pytest.fixture
def mock_storage_connection():
    """
    Fixture to mock storage connection in app.routers.health.check_storage_connection.
    """
    with patch("app.routers.health.check_storage_connection") as mock_check:
        yield mock_check

@pytest.fixture
def mock_blockchain_connection():
    """
    Fixture to mock blockchain connection in app.routers.health.check_blockchain_connection.
    """
    with patch("app.routers.health.check_blockchain_connection") as mock_check:
        yield mock_check
