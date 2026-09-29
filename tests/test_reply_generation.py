import pytest

import api.chat_engine
from api.chat_engine import REPLY_RESPONSE_FORMAT, ChatEngine, GeneratedReply, parse_generated_reply
from tests.fake_openai import FakeOpenAI


def _db_unavailable():
    raise RuntimeError("database unavailable in tests")


@pytest.fixture()
def engine(monkeypatch):
    monkeypatch.setattr(api.chat_engine, "get_session", _db_unavailable)
    monkeypatch.setenv("RECOMATE_EMOTION_ANALYZER", "keyword")
    # Pin models so a local .env can't collapse the fallback chain.
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "primary-model")
    monkeypatch.setenv("OPENAI_FALLBACK_CHAT_MODEL", "fallback-model")
    return ChatEngine()


def test_parse_generated_reply_reads_structured_output() -> None:
    reply = parse_generated_reply('{"reply": " それはうれしいね！！ ", "expression": "happy"}')

    assert reply == GeneratedReply("それはうれしいね！", "happy")


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"reply": "そっか。", "expression": "smug"}', GeneratedReply("そっか。", None)),
        ("そっか、今日はゆっくりしよう。", GeneratedReply("そっか、今日はゆっくりしよう。", None)),
        ('{"text": "wrong key"}', GeneratedReply('{"text": "wrong key"}', None)),
    ],
    ids=["unknown-expression", "plain-text", "unexpected-json"],
)
def test_parse_generated_reply_tolerates_non_conforming_output(content, expected) -> None:
    assert parse_generated_reply(content) == expected


def test_generation_requests_reply_and_expression_in_one_call(engine) -> None:
    client = FakeOpenAI(lambda _: {"reply": "それは疲れたね。", "expression": "sad"})

    reply = engine._call_language_model(client, [{"role": "user", "content": "疲れた"}])

    assert reply == GeneratedReply("それは疲れたね。", "sad")
    assert len(client.calls) == 1
    assert client.calls[0]["response_format"] is REPLY_RESPONSE_FORMAT
    assert client.calls[0]["model"] == engine.chat_model


def test_generation_moves_to_fallback_model_after_an_error(engine) -> None:
    def responder(call):
        if call["model"] == engine.chat_model:
            raise RuntimeError("primary down")
        return {"reply": "大丈夫、ここにいるよ。", "expression": "neutral"}

    client = FakeOpenAI(responder)

    reply = engine._call_language_model(client, [{"role": "user", "content": "眠れない"}])

    assert reply.text == "大丈夫、ここにいるよ。"
    assert [call["model"] for call in client.calls] == [engine.chat_model, engine.chat_fallback_model]


def test_turn_uses_generated_expression_or_falls_back_to_keywords(engine, monkeypatch) -> None:
    monkeypatch.setattr(ChatEngine, "_resolve_client", lambda self, api_key=None: object())

    monkeypatch.setattr(
        ChatEngine, "_call_language_model", lambda self, client, messages: GeneratedReply("やったね！", "surprised")
    )
    chosen = engine.handle_turn("試験に受かった")
    assert chosen.assistant_emotion["primary_emotions"] == ["surprised"]
    assert chosen.assistant_emotion["source"] == "llm"

    monkeypatch.setattr(
        ChatEngine, "_call_language_model", lambda self, client, messages: GeneratedReply("それは最高にうれしいね。")
    )
    missing = engine.handle_turn("試験に受かった")
    assert missing.assistant_emotion["primary_emotions"][0] == "happy"
    assert missing.assistant_emotion["source"] == "keyword"
