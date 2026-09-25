import numpy as np

from api.topic_bandit import TopicBandit


def test_record_selection_and_reward_update_share_the_same_topic_without_double_counting() -> None:
    bandit = TopicBandit(["仕事・学び"])

    selection = bandit.record_topic_selection("仕事・学び")
    assert selection is not None
    topic_idx = selection.topic_idx
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


def test_select_from_candidates_records_selection_and_returns_known_topic() -> None:
    bandit = TopicBandit(["仕事・学び", "趣味・好きなもの", "軽い雑談"], min_exploration_probability=0.0)

    selected = bandit.select_from_candidates(
        ["仕事・学び", "趣味・好きなもの"],
        features={"user_input": "仕事の話", "emotion": {"primary_emotions": ["sad"]}},
    )

    assert selected is not None
    topic_idx, topic = selected
    assert topic in {"仕事・学び", "趣味・好きなもの"}
    assert bandit.total_selections == 1
    assert bandit.counts[topic_idx] == 1


def test_select_from_candidates_learns_to_prefer_rewarded_topic() -> None:
    bandit = TopicBandit(
        ["仕事・学び", "趣味・好きなもの"],
        min_exploration_probability=0.0,
        recency_penalty=0.0,
        frequency_penalty=0.0,
    )
    features = {"user_input": "今日の話", "emotion": {"primary_emotions": ["neutral"]}}

    for _ in range(6):
        bandit.update(1, 0.95, features=features)
        bandit.update(0, 0.05, features=features)

    selected = bandit.select_from_candidates(["仕事・学び", "趣味・好きなもの"], features=features)

    assert selected is not None
    assert selected[1] == "趣味・好きなもの"


def test_select_from_candidates_ignores_unknown_topics() -> None:
    bandit = TopicBandit(["仕事・学び"])

    assert bandit.select_from_candidates(["存在しない話題"]) is None


def test_add_to_history_is_capped() -> None:
    bandit = TopicBandit(["仕事・学び"], max_history=5)

    for index in range(12):
        bandit.add_to_history(f"入力{index}", f"応答{index}", "仕事・学び", reward=0.5)

    assert len(bandit.conversation_history) == 5
    assert bandit.conversation_history[-1]["user_input"] == "入力11"


def test_update_uses_selection_time_context() -> None:
    bandit = TopicBandit(["仕事・学び", "軽い雑談"], min_exploration_probability=0.0)
    features = {"user_input": "仕事の話", "heuristic_scores": {"仕事・学び": 4.0, "軽い雑談": 0.5}}

    # Warm up so recency/popularity features are non-trivial.
    bandit.record_topic_selection("軽い雑談", features)
    selection = bandit.select_with_context(["仕事・学び", "軽い雑談"], features)
    assert selection is not None

    before = bandit.A_matrices[selection.topic_idx].copy()
    bandit.update(selection.topic_idx, 0.9, context=selection.context)

    np.testing.assert_allclose(
        bandit.A_matrices[selection.topic_idx] - before,
        np.outer(selection.context, selection.context),
    )
    # Recomputing after selection would see a different recency value.
    recomputed = bandit._get_feature_vector(selection.topic_idx, features)
    assert not np.allclose(recomputed, selection.context)


def test_heuristic_score_feature_is_scaled_per_topic() -> None:
    bandit = TopicBandit(["仕事・学び", "軽い雑談"])
    features = {"heuristic_scores": {"仕事・学び": 10.0, "軽い雑談": -2.0}}

    assert bandit._get_feature_vector(0, features)[1] == 1.0
    assert bandit._get_feature_vector(1, features)[1] == 0.0


def test_state_roundtrip_restores_learning_by_topic_name() -> None:
    source = TopicBandit(["仕事・学び", "趣味・好きなもの"])
    for _ in range(3):
        source.update(1, 0.9, features={"user_input": "映画"})

    restored = TopicBandit(["趣味・好きなもの", "新しい話題"])
    assert restored.load_state(source.to_state()) == 1

    np.testing.assert_allclose(restored.A_matrices[0], source.A_matrices[1])
    np.testing.assert_allclose(restored.b_vectors[0], source.b_vectors[1])
    assert restored.values[0] == source.values[1]
    np.testing.assert_allclose(restored.A_matrices[1], np.identity(restored.feature_dim))


def test_load_state_ignores_incompatible_payloads() -> None:
    bandit = TopicBandit(["仕事・学び"])
    state = bandit.to_state()
    state["feature_dim"] = 99

    assert bandit.load_state(state) == 0
    assert bandit.load_state({"version": 0}) == 0
