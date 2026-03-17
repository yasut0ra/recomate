from api.services import mood


def test_pick_state_prefers_trigger_mapping() -> None:
    assert mood._pick_state("success", "穏やか") == "陽気"


def test_pick_state_fallback_avoids_previous_state(monkeypatch) -> None:
    captured = {}

    def choose_first(options):
        captured["options"] = list(options)
        return options[0]

    monkeypatch.setattr(mood.random, "choice", choose_first)

    new_state = mood._pick_state(None, "穏やか")

    assert "穏やか" not in captured["options"]
    assert new_state in mood.AVAILABLE_STATES
    assert new_state != "穏やか"
