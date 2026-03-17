from datetime import datetime, timedelta, timezone
from uuid import uuid4

from api.db.models import Episode
from api.services.episodes import (
    build_episode_tags,
    compose_episode_text,
    parse_episode_text,
    select_recent_episode_context,
)


def test_compose_episode_text_creates_stable_transcript() -> None:
    transcript = compose_episode_text("映画の話をしたい", "どのシーンが良かった？")

    assert transcript == "User: 映画の話をしたい\nRecoMate: どのシーンが良かった？"


def test_build_episode_tags_keeps_compact_metadata() -> None:
    tags = build_episode_tags(
        topic_family="趣味・好きなもの",
        emotion_label="happy",
        mood_state="陽気",
        extra_tags=["auto_memory", "auto_memory"],
    )

    assert tags == [
        "topic:趣味・好きなもの",
        "emotion:happy",
        "mood:陽気",
        "auto_memory",
    ]


def test_parse_episode_text_splits_user_and_assistant_turns() -> None:
    parsed = parse_episode_text("User: 仕事がしんどい\nRecoMate: 無理ない範囲でいこう。")

    assert parsed["user_text"] == "仕事がしんどい"
    assert parsed["assistant_text"] == "無理ない範囲でいこう。"


def test_select_recent_episode_context_prefers_relevant_turns() -> None:
    base = datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc)
    episodes = [
        Episode(
            id=uuid4(),
            user_id=uuid4(),
            ts=base,
            text=compose_episode_text("残業つづきで疲れた", "つらかったね"),
            tags=["topic:仕事・学び"],
        ),
        Episode(
            id=uuid4(),
            user_id=uuid4(),
            ts=base + timedelta(minutes=5),
            text=compose_episode_text("映画の話をもっとしたい", "どのシーンが良かった？"),
            tags=["topic:趣味・好きなもの"],
        ),
        Episode(
            id=uuid4(),
            user_id=uuid4(),
            ts=base + timedelta(minutes=10),
            text=compose_episode_text("眠れなくて不安", "少しずつ整えよう"),
            tags=["topic:悩み・気持ち整理"],
        ),
    ]

    context = select_recent_episode_context(episodes[::-1], query="映画", limit=2)

    assert len(context) == 2
    assert any(item["topic"] == "趣味・好きなもの" for item in context)
    assert any(item["user_text"] == "映画の話をもっとしたい" for item in context)
