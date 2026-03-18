from api.services.chat_payloads import build_chat_history_entry, build_chat_response_payload


def test_build_chat_response_payload_separates_user_and_assistant_emotions() -> None:
    user_emotion = {"primary_emotions": ["sad"], "intensity": 0.82}
    assistant_emotion = {"primary_emotions": ["happy"], "intensity": 0.55}

    payload = build_chat_response_payload(
        response="それはしんどかったね。今は少し力を抜いていて。",
        user_emotion=user_emotion,
        assistant_emotion=assistant_emotion,
        reward=0.73,
        conversation_history=[],
        turn_metadata={"topic": "悩み・気持ち整理"},
    )

    assert payload["user_emotion"] == user_emotion
    assert payload["assistant_emotion"] == assistant_emotion
    assert payload["emotion"] == assistant_emotion
    assert payload["reward"] == 0.73


def test_build_chat_history_entry_keeps_assistant_emotion_as_legacy_alias() -> None:
    user_emotion = {"primary_emotions": ["sad"], "intensity": 0.7}
    assistant_emotion = {"primary_emotions": ["angry"], "intensity": 0.65}

    entry = build_chat_history_entry(
        user_input="それは納得いかないよ",
        response="それは腹が立つよね。その引っかかりは軽く流せないやつだ。",
        user_emotion=user_emotion,
        assistant_emotion=assistant_emotion,
        reward=0.64,
        timestamp=123.0,
    )

    assert entry["user_emotion"] == user_emotion
    assert entry["assistant_emotion"] == assistant_emotion
    assert entry["emotion"] == assistant_emotion
    assert entry["reward"] == 0.64
