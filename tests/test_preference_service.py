from uuid import uuid4

from api.db.models import Preference
from api.services.preferences import _apply_feedback_snapshot, describe_preference_profile


def test_apply_feedback_snapshot_updates_tone_humor_and_style_notes() -> None:
    profile = {
        "tone": 0.6,
        "humor": 0.5,
        "style_notes": {
            "length_bias": 0.0,
            "metaphor_bias": 0.0,
            "formality_bias": 0.0,
            "feedback_count": 0,
        },
    }

    updated = _apply_feedback_snapshot(
        profile,
        like=True,
        tone_delta=0.1,
        length_delta=-0.2,
        metaphor_delta=0.3,
    )

    assert updated["tone"] == 0.7
    assert updated["humor"] > profile["humor"]
    assert updated["style_notes"]["length_bias"] == -0.2
    assert updated["style_notes"]["metaphor_bias"] == 0.3
    assert updated["style_notes"]["feedback_count"] == 1


def test_describe_preference_profile_derives_style_summary() -> None:
    preference = Preference(
        user_id=uuid4(),
        tone=0.82,
        humor=0.25,
        style_notes={
            "length_bias": -0.5,
            "metaphor_bias": -0.4,
            "formality_bias": 0.4,
            "feedback_count": 3,
        },
        tts_voice="voicevox:normal",
        boundaries_json={},
    )

    profile = describe_preference_profile(preference)

    assert profile["style_summary"]["tone_style"] == "親密でやわらかい"
    assert profile["style_summary"]["humor_style"] == "冗談は控えめにする"
    assert profile["style_summary"]["length_style"] == "かなりコンパクトに返す"
    assert profile["style_summary"]["metaphor_style"] == "比喩はほぼ使わない"
