from datetime import datetime, timezone
from uuid import uuid4

from api.db.models import Memory
from api.services.memory import (
    _extract_keywords,
    _extract_memory_source_text,
    _generate_summary,
    _looks_like_duplicate_memory,
    select_relevant_memories,
    should_promote_episode_to_memory,
)


def test_generate_summary_returns_placeholder_for_empty_text() -> None:
    assert _generate_summary("   ") == "_空のメッセージ_"


def test_generate_summary_truncates_with_ellipsis() -> None:
    assert _generate_summary("abcdef", max_length=5) == "abcd…"


def test_extract_keywords_normalizes_and_ranks_by_frequency() -> None:
    text = "AI ai 猫猫 猫猫 旅行 旅行 旅行 a"

    assert _extract_keywords(text, limit=3) == ["旅行", "ai", "猫猫"]


def test_select_relevant_memories_prioritises_query_match_and_pinned() -> None:
    base_time = datetime(2026, 3, 18, tzinfo=timezone.utc)
    memories = [
        Memory(
            id=uuid4(),
            user_id=uuid4(),
            summary_md="映画の感想まとめ",
            keywords=["映画", "感想"],
            pinned=False,
            created_at=base_time,
        ),
        Memory(
            id=uuid4(),
            user_id=uuid4(),
            summary_md="仕事で疲れた週の記録",
            keywords=["仕事", "疲れた"],
            pinned=True,
            created_at=base_time,
        ),
        Memory(
            id=uuid4(),
            user_id=uuid4(),
            summary_md="散歩メモ",
            keywords=["散歩"],
            pinned=False,
            created_at=base_time,
        ),
    ]

    selected = select_relevant_memories(memories, query="映画", limit=2)

    assert selected[0].summary_md == "映画の感想まとめ"
    assert len(selected) == 2


def test_extract_memory_source_text_prefers_user_portion_from_transcript() -> None:
    transcript = "User: 映画の話をもっとしたい\nRecoMate: どのシーンが良かった？"

    assert _extract_memory_source_text(transcript) == "映画の話をもっとしたい"


def test_should_promote_episode_to_memory_requires_meaningful_turn() -> None:
    meaningful = should_promote_episode_to_memory(
        "User: 上司との会議が長引いてしんどかった\nRecoMate: 無理のないところから整理しよう。",
        topic_family="仕事・学び",
        emotion_payload={"intensity": 0.72},
    )
    casual = should_promote_episode_to_memory(
        "User: ひまだね\nRecoMate: そうだね。",
        topic_family="軽い雑談",
        emotion_payload={"intensity": 0.4},
    )

    assert meaningful is True
    assert casual is False


def test_duplicate_memory_detection_avoids_repeated_summary() -> None:
    base_time = datetime(2026, 3, 18, tzinfo=timezone.utc)
    existing = [
        Memory(
            id=uuid4(),
            user_id=uuid4(),
            summary_md="映画の感想まとめ",
            keywords=["映画", "感想", "週末"],
            pinned=False,
            created_at=base_time,
        ),
    ]

    assert _looks_like_duplicate_memory(existing, "映画の感想まとめ", ["映画", "感想", "週末"]) is True
