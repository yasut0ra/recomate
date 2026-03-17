from datetime import datetime, timezone
from uuid import uuid4

from api.db.models import Memory
from api.services.memory import _extract_keywords, _generate_summary, select_relevant_memories


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
