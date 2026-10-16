"""Basic API tests. Run with: pytest -q

These tests use FastAPI's TestClient and monkeypatch the AI service so they
do not call OpenAI. Set NOT_TEST_DB to a temp file before importing the app.
"""
from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def client():
    tmpdir = tempfile.mkdtemp(prefix="not_test_")
    db_file = Path(tmpdir) / "test.db"
    os.environ["DB_PATH"] = str(db_file)
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
    os.environ.setdefault("OPENAI_MODEL", "gpt-4o-mini")

    # Import after env is set.
    from app import config as config_module
    config_module.get_settings.cache_clear()

    from app import main as main_module
    importlib.reload(main_module)
    from fastapi.testclient import TestClient
    with TestClient(main_module.app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "model" in body


def test_create_and_list_conversation(client):
    r = client.post("/api/conversations")
    assert r.status_code == 201
    cid = r.json()["id"]

    r2 = client.get("/api/conversations")
    assert r2.status_code == 200
    assert any(c["id"] == cid for c in r2.json())


def test_rename_conversation(client):
    cid = client.post("/api/conversations").json()["id"]
    r = client.patch(f"/api/conversations/{cid}", json={"title": "Renamed"})
    assert r.status_code == 200
    assert r.json()["title"] == "Renamed"


def test_delete_conversation(client):
    cid = client.post("/api/conversations").json()["id"]
    r = client.delete(f"/api/conversations/{cid}")
    assert r.status_code == 204
    r2 = client.get(f"/api/conversations/{cid}")
    assert r2.status_code == 404


def test_chat_requires_message(client):
    r = client.post("/api/chat", json={"message": ""})
    assert r.status_code == 422


def test_chat_missing_conversation(client):
    r = client.post("/api/chat", json={"conversation_id": 99999, "message": "hi"})
    assert r.status_code == 404


def test_chat_with_mocked_ai(client, monkeypatch):
    async def fake_generate_reply(history, user_message, language="auto"):
        return ("Hello from NOT (mocked).", "gpt-4o-mini")

    from app.routes import chat as chat_route
    monkeypatch.setattr(chat_route, "generate_reply", fake_generate_reply)

    r = client.post("/api/chat", json={"message": "hi", "language": "en"})
    assert r.status_code == 200
    body = r.json()
    assert "mocked" in body["reply"]
    assert body["conversation_id"] > 0