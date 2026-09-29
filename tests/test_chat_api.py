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
from api.chat_engine import ChatEngine, GeneratedReply
from api.main import app

FAKE_REPLY = "それは大変だったね。今日はゆっくり休んでいいと思うよ。"
FAKE_GENERATION = GeneratedReply(FAKE_REPLY, "sad")


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
    monkeypatch.setattr(ChatEngine, "_call_language_model", lambda self, client, messages: FAKE_GENERATION)
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


def _topic_values(test_client):
    stats = test_client.get("/api/topics/stats").json()
    return {topic: metric["value"] for topic, metric in stats["topics"].items()}


def test_chat_turn_metadata_exposes_turn_id_and_topic(client) -> None:
    payload = client.post("/api/chat", json={"text": "仕事の会議で疲れた"}).json()

    metadata = payload["turn_metadata"]
    assert metadata["turn_id"]
    assert metadata["topic"]
    assert metadata["feedback_enabled"] is True
    assert payload["conversation_history"][-1]["turn_id"] == metadata["turn_id"]
    assert payload["conversation_history"][-1]["topic"] == metadata["topic"]


def test_bandit_learns_from_the_users_next_message(client) -> None:
    user_id = str(uuid.uuid4())
    first = client.post("/api/chat", json={"text": "仕事の会議で疲れた", "user_id": user_id}).json()
    topic = first["turn_metadata"]["topic"]

    # No reaction yet, so nothing has been learned.
    assert all(value == 0.0 for value in _topic_values(client).values())

    client.post("/api/chat", json={"text": "そうそう、それで上司にも話してみたんだ", "user_id": user_id})

    assert _topic_values(client)[topic] > 0.0


def test_feedback_endpoint_applies_once(client, isolated_bandit_state) -> None:
    user_id = str(uuid.uuid4())
    turn = client.post("/api/chat", json={"text": "映画を観てきた", "user_id": user_id}).json()["turn_metadata"]

    liked = client.post(
        "/api/chat/feedback",
        json={"turn_id": turn["turn_id"], "like": True, "user_id": user_id},
    )
    assert liked.status_code == 200
    assert liked.json() == {
        "turn_id": turn["turn_id"],
        "topic": turn["topic"],
        "applied": True,
        "reward": 1.0,
        "reason": None,
    }
    assert _topic_values(client)[turn["topic"]] > 0.0
    assert isolated_bandit_state.exists()

    repeated = client.post(
        "/api/chat/feedback",
        json={"turn_id": turn["turn_id"], "like": False, "user_id": user_id},
    ).json()
    assert repeated["applied"] is False
    assert repeated["reason"] == "already_rated"


def test_feedback_for_unknown_turn_or_other_user_is_404(client) -> None:
    user_id = str(uuid.uuid4())
    turn_id = client.post("/api/chat", json={"text": "雑談しよ", "user_id": user_id}).json()["turn_metadata"]["turn_id"]

    assert client.post("/api/chat/feedback", json={"turn_id": "missing", "like": True}).status_code == 404
    other_user = client.post(
        "/api/chat/feedback",
        json={"turn_id": turn_id, "like": True, "user_id": str(uuid.uuid4())},
    )
    assert other_user.status_code == 404


def test_feedback_on_fallback_reply_does_not_train(offline_client) -> None:
    turn = offline_client.post("/api/chat", json={"text": "眠れなくてつらい"}).json()["turn_metadata"]
    assert turn["feedback_enabled"] is False

    result = offline_client.post("/api/chat/feedback", json={"turn_id": turn["turn_id"], "like": True}).json()

    assert result["applied"] is False
    assert result["reason"] == "not_learnable"
    assert all(value == 0.0 for value in _topic_values(offline_client).values())


def test_learning_paused_blocks_implicit_and_explicit_learning(client, monkeypatch) -> None:
    original = ChatEngine._default_runtime_context

    def paused_context(self, user_id, current_text=""):
        context = original(self, user_id)
        context["consent"]["learning_paused"] = True
        return context

    monkeypatch.setattr(ChatEngine, "_build_runtime_context", paused_context)

    first = client.post("/api/chat", json={"text": "仕事の会議で疲れた"}).json()["turn_metadata"]
    second = client.post("/api/chat", json={"text": "そうそう、それでね"}).json()["turn_metadata"]
    feedback = client.post("/api/chat/feedback", json={"turn_id": second["turn_id"], "like": True}).json()

    assert first["feedback_enabled"] is False
    assert feedback["applied"] is False
    assert all(value == 0.0 for value in _topic_values(client).values())


def test_bandit_state_survives_engine_restart(client, isolated_bandit_state) -> None:
    turn = client.post("/api/chat", json={"text": "推しのライブに行った"}).json()["turn_metadata"]
    client.post("/api/chat/feedback", json={"turn_id": turn["turn_id"], "like": True})
    learned = _topic_values(client)[turn["topic"]]

    restarted = ChatEngine()

    assert restarted.topic_summary()["topics"][turn["topic"]]["value"] == learned


def test_continuation_keeps_topic_without_database(client) -> None:
    user_id = str(uuid.uuid4())
    first = client.post("/api/chat", json={"text": "上司との会議がしんどかった", "user_id": user_id}).json()
    second = client.post("/api/chat", json={"text": "その続きなんだけど", "user_id": user_id}).json()

    assert second["turn_metadata"]["topic"] == first["turn_metadata"]["topic"]


def _engine_with_llm_reaction(monkeypatch, reaction_score):
    from tests.fake_openai import FakeOpenAI, schema_of

    def responder(call):
        payload = {"emotion": "sad", "secondary_emotion": None, "intensity": 0.7, "reason": "疲れている"}
        if "reaction" in schema_of(call)["properties"]:
            label = "engaged" if reaction_score >= 0.5 else "dismissive"
            payload["reaction"] = {"label": label, "score": reaction_score, "reason": "テスト"}
        return payload

    fake = FakeOpenAI(responder)
    _isolate_backend(monkeypatch)
    monkeypatch.delenv("RECOMATE_EMOTION_ANALYZER", raising=False)
    monkeypatch.setattr(ChatEngine, "_resolve_client", lambda self, api_key=None: fake)
    monkeypatch.setattr(ChatEngine, "_call_language_model", lambda self, client, messages: FAKE_GENERATION)
    return ChatEngine(), fake


@pytest.mark.parametrize("reaction_score", [1.0, 0.0])
def test_llm_reaction_score_drives_bandit_learning(monkeypatch, reaction_score) -> None:
    engine, fake = _engine_with_llm_reaction(monkeypatch, reaction_score)

    first = engine.handle_turn("仕事の会議で疲れた")
    second = engine.handle_turn("うーん")

    topic = first.turn_metadata["topic"]
    learned = engine.topic_summary()["topics"][topic]["value"]
    expected = 0.1 * (0.35 * first.reward + 0.65 * reaction_score)

    assert first.user_emotion["source"] == "llm"
    assert second.turn_metadata["previous_turn_reaction"]["score"] == reaction_score
    assert learned == pytest.approx(expected, abs=1e-3)
    # One analysis call per turn; the reply's expression comes from generation.
    assert len(fake.calls) == 2
    assert first.assistant_emotion["primary_emotions"] == ["sad"]
    assert first.assistant_emotion["source"] == "llm"
