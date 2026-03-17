from api.services.conversation_planner import ConversationPlanner


def test_planner_picks_work_topic_from_japanese_keywords() -> None:
    planner = ConversationPlanner()

    plan = planner.plan(
        "上司との会議が長引いて、仕事でかなり疲れたよ。",
        {"primary_emotions": ["sad"], "intensity": 0.7},
    )

    assert plan.topic_family == "仕事・学び"
    assert "安心感" in plan.response_intent or "受け止める" in plan.response_intent


def test_planner_keeps_previous_topic_when_user_signals_continuity() -> None:
    planner = ConversationPlanner()
    recent_history = [
        {"topic": "人間関係", "user_input": "友達と気まずい", "response": "それは気になるね。"},
    ]

    plan = planner.plan(
        "その続きなんだけど、まだ友達に返事できてないんだ。",
        {"primary_emotions": ["sad"], "intensity": 0.6},
        recent_history=recent_history,
    )

    assert plan.topic_family == "人間関係"
    assert plan.continuity == "継続"


def test_planner_avoids_repeating_last_topic_without_signal() -> None:
    planner = ConversationPlanner()
    recent_history = [
        {"topic": "仕事・学び", "user_input": "残業だった", "response": "大変だったね。"},
        {"topic": "仕事・学び", "user_input": "会議が多い", "response": "負担が大きいね。"},
    ]

    plan = planner.plan(
        "最近見た映画がすごくよくて、音楽も最高だった。",
        {"primary_emotions": ["happy"], "intensity": 0.8},
        recent_history=recent_history,
    )

    assert plan.topic_family == "趣味・好きなもの"
    assert plan.continuity == "話題転換"


def test_planner_uses_supportive_intent_for_negative_advice_request() -> None:
    planner = ConversationPlanner()

    plan = planner.plan(
        "不安でつらいんだけど、どうしたら少し楽になるかな。",
        {"primary_emotions": ["sad"], "intensity": 0.75},
    )

    assert plan.topic_family == "悩み・気持ち整理"
    assert plan.response_intent == "共感しつつ整理する"
    assert "確認" in plan.follow_up_style
