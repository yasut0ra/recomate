from api.services.rewarding import calculate_response_reward


def test_reward_prefers_supportive_companion_reply_for_negative_user_input() -> None:
    supportive = calculate_response_reward(
        user_text="今日はずっとしんどくてつらい。",
        response_text="それはしんどかったね。今は無理に整えなくて大丈夫だよ。",
        user_emotion={"primary_emotions": ["sad"], "intensity": 0.82},
        assistant_emotion={"primary_emotions": ["sad"], "intensity": 0.58},
    )
    interrogative = calculate_response_reward(
        user_text="今日はずっとしんどくてつらい。",
        response_text="何が原因？どうしてそうなったの？",
        user_emotion={"primary_emotions": ["sad"], "intensity": 0.82},
        assistant_emotion={"primary_emotions": ["neutral"], "intensity": 0.5},
    )

    assert supportive > interrogative
    assert supportive > 0.6


def test_reward_stays_in_zero_to_one_range() -> None:
    reward = calculate_response_reward(
        user_text="うれしい！",
        response_text="それはうれしいね。こっちまで明るくなるよ。",
        user_emotion={"primary_emotions": ["happy"], "intensity": 0.9},
        assistant_emotion={"primary_emotions": ["happy"], "intensity": 0.7},
    )

    assert 0.0 <= reward <= 1.0
