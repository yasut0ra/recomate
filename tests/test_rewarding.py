from api.services.rewarding import (
    blend_turn_reward,
    calculate_engagement_reward,
    calculate_response_reward,
)


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


def test_engagement_reward_separates_engaged_and_dismissive_reactions() -> None:
    engaged = calculate_engagement_reward(next_user_text="そうそう、それで上司にも相談してみたんだけど聞いてくれる？")
    dismissive = calculate_engagement_reward(next_user_text="もういい、別の話しよ")
    minimal = calculate_engagement_reward(next_user_text="うん。")

    assert engaged > 0.7
    assert dismissive < 0.3
    assert dismissive < minimal < engaged


def test_engagement_reward_credits_mood_recovery() -> None:
    recovered = calculate_engagement_reward(
        next_user_text="ちょっと楽になったかも",
        previous_user_emotion={"primary_emotions": ["sad"]},
        next_user_emotion={"primary_emotions": ["neutral"]},
    )
    worsened = calculate_engagement_reward(
        next_user_text="ちょっと楽になったかも",
        previous_user_emotion={"primary_emotions": ["neutral"]},
        next_user_emotion={"primary_emotions": ["sad"]},
    )

    assert recovered > worsened


def test_blend_turn_reward_weights_user_reaction_over_self_assessment() -> None:
    assert blend_turn_reward(1.0, 0.0) < 0.5
    assert blend_turn_reward(0.0, 1.0) > 0.5
    assert 0.0 <= blend_turn_reward(0.4, 0.9) <= 1.0
