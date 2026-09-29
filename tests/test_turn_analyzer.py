import json

import pytest

from api.turn_analyzer import DEFAULT_ANALYSIS_MODEL, TurnAnalyzer
from tests.fake_openai import FakeOpenAI, schema_of


@pytest.fixture(autouse=True)
def llm_mode(monkeypatch):
    monkeypatch.delenv("RECOMATE_EMOTION_ANALYZER", raising=False)
    monkeypatch.delenv("OPENAI_ANALYSIS_MODEL", raising=False)


def test_llm_emotion_is_mapped_to_keyword_payload_shape() -> None:
    client = FakeOpenAI(lambda _: {
        "emotion": "happy",
        "secondary_emotion": "sad",
        "intensity": 1.4,
        "reason": "嬉しさと寂しさが混ざる",
    })

    analysis = TurnAnalyzer().analyze_turn(client, user_text="卒業できて嬉しいけど、みんなと離れるのは寂しい")

    assert analysis.emotion["primary_emotions"] == ["happy", "sad"]
    assert analysis.emotion["intensity"] == 1.0
    assert analysis.emotion["emotion_change"] == "揺れあり"
    assert analysis.emotion["source"] == "llm"
    assert analysis.reaction_score is None

    call = client.calls[0]
    assert call["model"] == DEFAULT_ANALYSIS_MODEL
    assert call["response_format"]["json_schema"]["strict"] is True
    assert "reaction" not in schema_of(call)["properties"]
    assert client.options == [{"timeout": 8.0, "max_retries": 0}]


def test_reaction_is_judged_in_the_same_call_when_previous_reply_is_given() -> None:
    client = FakeOpenAI(lambda _: {
        "emotion": "neutral",
        "secondary_emotion": None,
        "intensity": 0.4,
        "reason": "落ち着いている",
        "reaction": {"label": "dismissive", "score": 0.1, "reason": "話がずれている"},
    })

    analysis = TurnAnalyzer().analyze_turn(
        client,
        user_text="いや、そういう話じゃなくてさ",
        previous_user_text="上司に怒られた",
        previous_reply="それなら今日は美味しいものを食べよう！",
    )

    assert len(client.calls) == 1
    assert "reaction" in schema_of(client.calls[0])["properties"]
    sent = json.loads(client.calls[0]["messages"][1]["content"])
    assert sent["previous_assistant_reply"] == "それなら今日は美味しいものを食べよう！"
    assert analysis.reaction_score == 0.1
    assert analysis.reaction == {"label": "dismissive", "score": 0.1, "reason": "話がずれている"}


def test_catches_what_keywords_miss() -> None:
    # 「落ち込んでない」 still contains the keyword stem 落ち込, so keywords say sad.
    text = "もう落ち込んでないよ、むしろスッキリした"
    keyword = TurnAnalyzer().analyze_turn(None, user_text=text)
    llm = TurnAnalyzer().analyze_turn(
        FakeOpenAI(lambda _: {"emotion": "happy", "secondary_emotion": None, "intensity": 0.6, "reason": "解放感"}),
        user_text=text,
    )

    assert keyword.emotion["primary_emotions"][0] == "sad"
    assert llm.emotion["primary_emotions"][0] == "happy"


@pytest.mark.parametrize(
    "client",
    [
        FakeOpenAI(error=TimeoutError("slow")),
        FakeOpenAI(lambda _: "not json"),
        FakeOpenAI(lambda _: {"emotion": "joyful", "secondary_emotion": None, "intensity": 0.5, "reason": ""}),
        FakeOpenAI(lambda _: {"emotion": "happy", "secondary_emotion": None, "intensity": 0.5, "reason": ""}),
    ],
    ids=["error", "malformed", "unknown-label", "missing-reaction"],
)
def test_falls_back_to_keywords_on_bad_llm_output(client) -> None:
    analysis = TurnAnalyzer().analyze_turn(
        client,
        user_text="そうそう、それでね、もっと話したいことがあるんだ",
        previous_user_text="今日は楽しかった",
        previous_reply="それは良かったね。",
    )

    assert analysis.emotion["source"] == "keyword"
    assert analysis.reaction_score is not None
    assert analysis.reaction_score > 0.5


def test_keyword_mode_and_missing_client_skip_the_llm(monkeypatch) -> None:
    client = FakeOpenAI(lambda _: pytest.fail("LLM should not be called"))
    assert TurnAnalyzer().analyze_turn(None, user_text="楽しい").emotion["source"] == "keyword"

    monkeypatch.setenv("RECOMATE_EMOTION_ANALYZER", "keyword")
    analysis = TurnAnalyzer().analyze_turn(client, user_text="楽しい")

    assert analysis.emotion["source"] == "keyword"
    assert client.calls == []


def test_analysis_model_is_configurable(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_ANALYSIS_MODEL", "my-small-model")
    client = FakeOpenAI(lambda _: {"emotion": "neutral", "secondary_emotion": None, "intensity": 0.3, "reason": ""})

    TurnAnalyzer().analyze_text(client, "こんにちは")

    assert client.calls[0]["model"] == "my-small-model"
