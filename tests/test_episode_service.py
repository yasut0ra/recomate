from api.services.episodes import build_episode_tags, compose_episode_text


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
