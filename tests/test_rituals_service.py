from api.services.rituals import (
    DEFAULT_MORNING_SCRIPTS,
    _extract_script_mapping,
    _resolve_events,
    _resolve_script,
)


def test_extract_script_mapping_flattens_nested_yaml() -> None:
    raw_yaml = """
morning:
  穏やか: 深呼吸から始めよう
night:
  ツン: 片付けたら寝なさい
"""

    assert _extract_script_mapping(raw_yaml) == {
        "穏やか": "深呼吸から始めよう",
        "ツン": "片付けたら寝なさい",
    }


def test_extract_script_mapping_returns_empty_dict_for_invalid_yaml() -> None:
    assert _extract_script_mapping(":\n  - broken") == {}


def test_resolve_script_prefers_override_and_falls_back() -> None:
    mood, script = _resolve_script(DEFAULT_MORNING_SCRIPTS, {"穏やか": "今日は静かに行こう"}, "穏やか")
    assert (mood, script) == ("穏やか", "今日は静かに行こう")

    fallback_mood, fallback_script = _resolve_script({}, {}, "未定義")
    assert (fallback_mood, fallback_script) == ("未定義", "")


def test_resolve_events_falls_back_to_calm_when_mood_is_unknown() -> None:
    events = _resolve_events("morning", "未定義")

    assert events == [
        {"event": "face", "value": "smile_soft"},
        {"event": "eye", "value": "blink_normal"},
        {"event": "mouth", "value": "a_i_u"},
    ]
