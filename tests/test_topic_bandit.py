from api.topic_bandit import TopicBandit


def test_record_selection_and_reward_update_share_the_same_topic_without_double_counting() -> None:
    bandit = TopicBandit(["仕事・学び"], client=None)

    topic_idx = bandit.record_topic_selection("仕事・学び")
    assert topic_idx == 0

    bandit.update(
        topic_idx,
        0.78,
        features={
            "user_input": "仕事でかなり疲れた",
            "context_text": "それはしんどかったね。今は無理に整えなくて大丈夫だよ。",
            "emotion": {"primary_emotions": ["sad"], "intensity": 0.7},
        },
    )

    stats = bandit.get_topic_stats()["仕事・学び"]

    assert stats["count"] == 1
    assert stats["frequency"] == 1
    assert stats["value"] > 0.0
