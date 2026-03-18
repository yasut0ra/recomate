from api.services.text_cleanup import clean_assistant_response


def test_clean_assistant_response_removes_stray_brackets_before_terminal_punctuation() -> None:
    text = "もちろん、直しておくね。ここはすっきり、軽く安心できる返しに整えるよ】【。"

    cleaned = clean_assistant_response(text)

    assert cleaned == "もちろん、直しておくね。ここはすっきり、軽く安心できる返しに整えるよ。"


def test_clean_assistant_response_preserves_legitimate_quotes() -> None:
    text = "「それはよかったね」って言いたくなるよ。"

    cleaned = clean_assistant_response(text)

    assert cleaned == text


def test_clean_assistant_response_trims_unmatched_edge_brackets() -> None:
    text = "】少しずつで大丈夫だよ。"

    cleaned = clean_assistant_response(text)

    assert cleaned == "少しずつで大丈夫だよ。"
