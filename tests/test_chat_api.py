"""Endpoint tests for the chat orchestration API.

The OpenAI call and the database are stubbed out: `_call_language_model`
returns a fixed reply and `get_session` raises, exercising the degraded-mode
paths that local development without Postgres also uses.
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

import api.chat_engine
import api.main
from api.chat_engine import ChatEngine
from api.main import app

FAKE_REPLY = "それは大変だったね。今日はゆっくり休んでいいと思うよ。"


def _db_unavailable():
    raise RuntimeError("database unavailable in tests")


def _isolate_backend(monkeypatch):
    monkeypatch.setenv("ENABLE_TTS", "false")
    monkeypatch.setattr(api.chat_engine, "get_session", _db_unavailable)
    monkeypatch.setattr(api.main, "get_session", _db_unavailable)


@pytest.fixture()
def client(monkeypatch):
    """TestClient with a fake LLM and no database."""
    _isolate_backend(monkeypatch)
    monkeypatch.setattr(ChatEngine, "_resolve_client", lambda self, api_key=None: object())
    monkeypatch.setattr(ChatEngine, "_call_language_model", lambda self, client, messages: FAKE_REPLY)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def offline_client(monkeypatch):
    """TestClient with no LLM client at all (fallback responses)."""
    _isolate_backend(monkeypatch)
    monkeypatch.setattr(ChatEngine, "_resolve_client", lambda self, api_key=None: None)
    with TestClient(app) as test_client:
        yield test_client


def test_chat_returns_full_payload(client) -> None:
    response = client.post("/api/chat", json={"text": "今日は仕事でかなり疲れたよ"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == FAKE_REPLY
    assert payload["user_emotion"]["primary_emotions"][0] == "sad"
    assert isinstance(payload["reward"], float)
    assert len(payload["conversation_history"]) == 1
    entry = payload["conversation_history"][0]
    assert entry["user_input"] == "今日は仕事でかなり疲れたよ"
    assert entry["response"] == FAKE_REPLY


def test_chat_histories_are_isolated_per_user(client) -> None:
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())

    client.post("/api/chat", json={"text": "Aの秘密の話", "user_id": user_a})
    response_b = client.post("/api/chat", json={"text": "Bはゲームの話", "user_id": user_b})

    history_b = response_b.json()["conversation_history"]
    assert len(history_b) == 1
    assert all("Aの秘密" not in entry["user_input"] for entry in history_b)

    response_a2 = client.post("/api/chat", json={"text": "続きなんだけど", "user_id": user_a})
    history_a = response_a2.json()["conversation_history"]
    assert [entry["user_input"] for entry in history_a] == ["Aの秘密の話", "続きなんだけど"]


def test_chat_falls_back_without_llm_and_skips_bandit_learning(offline_client) -> None:
    response = offline_client.post("/api/chat", json={"text": "眠れなくてつらい"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"]
    assert isinstance(payload["reward"], float)

    stats = offline_client.get("/api/topics/stats").json()
    assert all(metric["value"] == 0.0 for metric in stats["topics"].values())


def test_health_reports_subsystem_status(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["database_connected"] is False
    assert {"llm_configured", "tts_enabled", "transcription_available"} <= set(payload.keys())


def test_websocket_chat_roundtrip_and_validation(client) -> None:
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_text("not-json")
        assert "error" in websocket.receive_json()

        websocket.send_text(json.dumps({"userId": str(uuid.uuid4())}))
        assert "error" in websocket.receive_json()

        websocket.send_text(json.dumps({"text": "今日は嬉しいことがあった", "userId": str(uuid.uuid4())}))
        payload = websocket.receive_json()
        assert payload["response"] == FAKE_REPLY
        assert payload["user_emotion"]["primary_emotions"][0] == "happy"


def test_analyze_emotion_endpoint(client) -> None:
    response = client.post("/api/analyze-emotion", json={"text": "むかつくことがあった"})

    assert response.status_code == 200
    assert response.json()["emotion"] == "angry"
