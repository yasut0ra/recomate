from api.services.memory import _extract_keywords, _generate_summary


def test_generate_summary_returns_placeholder_for_empty_text() -> None:
    assert _generate_summary("   ") == "_空のメッセージ_"


def test_generate_summary_truncates_with_ellipsis() -> None:
    assert _generate_summary("abcdef", max_length=5) == "abcd…"


def test_extract_keywords_normalizes_and_ranks_by_frequency() -> None:
    text = "AI ai 猫猫 猫猫 旅行 旅行 旅行 a"

    assert _extract_keywords(text, limit=3) == ["旅行", "ai", "猫猫"]
