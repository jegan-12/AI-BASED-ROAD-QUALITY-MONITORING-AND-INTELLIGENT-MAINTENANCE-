import os
import io
import pytest
from PIL import Image
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET", "test-only-secret-" * 4)
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key-" * 4)
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("INFERENCE_MODE", "demo")

from backend.app.config import settings
from backend.app.db import Base, make_engine, get_db
from backend.app.models import User
from backend.app.security import password_hash


@pytest.fixture
def factory(tmp_path):
    engine = make_engine("sqlite:///" + str(tmp_path / "test.db"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings().media_dir = tmp_path / "media"
    settings().media_dir.mkdir()
    with factory() as db:
        for role in ("admin", "viewer", "inspector"):
            db.add(User(id=role, username=role, role=role, password_hash=password_hash.hash("test-password-123")))
        db.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def client(factory):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    def token(role="admin"):
        result = client.post("/api/auth/token", data={"username": role, "password": "test-password-123"})
        assert result.status_code == 200
        return {"Authorization": "Bearer " + result.json()["access_token"]}
    return token


@pytest.fixture
def image_bytes():
    out = io.BytesIO()
    Image.new("RGB", (240, 120), "gray").save(out, "JPEG")
    return out.getvalue()

