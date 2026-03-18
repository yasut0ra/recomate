from api.emotion_analyzer import EmotionAnalyzer


def test_analyze_emotion_detects_japanese_positive_text() -> None:
    analyzer = EmotionAnalyzer()

    emotion = analyzer.analyze_emotion("今日は本当にうれしいし、めっちゃ楽しい気分！")

    assert emotion["primary_emotions"][0] == "happy"
    assert emotion["intensity"] > 0.6


def test_get_emotion_expression_returns_supported_hint() -> None:
    analyzer = EmotionAnalyzer()

    expression = analyzer.get_emotion_expression({"primary_emotions": ["sad"], "intensity": 0.7})

    assert "悲しい" in expression


def test_analyze_emotion_detects_angry_assistant_phrase() -> None:
    analyzer = EmotionAnalyzer()

    emotion = analyzer.analyze_emotion("それは腹が立つよね。その引っかかりは軽く流せないやつだ。")

    assert emotion["primary_emotions"][0] == "angry"
    assert emotion["intensity"] > 0.5
