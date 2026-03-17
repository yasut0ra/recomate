from datetime import datetime, timezone
from uuid import uuid4

from api.db.models import Episode
from api.services.album import _resolve_reference_datetime, _summarise_episodes


def test_resolve_reference_datetime_parses_explicit_week_id() -> None:
    week_id, week_start, week_end = _resolve_reference_datetime("2026-W03")

    assert week_id == "2026-W03"
    assert week_start == datetime(2026, 1, 12, tzinfo=timezone.utc)
    assert week_end == datetime(2026, 1, 19, tzinfo=timezone.utc)


def test_resolve_reference_datetime_rejects_invalid_format() -> None:
    try:
        _resolve_reference_datetime("2026-03")
    except ValueError as exc:
        assert "Invalid week_id format" in str(exc)
    else:
        raise AssertionError("ValueError was not raised")


def test_summarise_episodes_collects_top_entries_and_keywords() -> None:
    base_time = datetime(2026, 3, 18, tzinfo=timezone.utc)
    episodes = [
        Episode(id=uuid4(), user_id=uuid4(), ts=base_time, text="桜道 散歩道 朝会", tags=[]),
        Episode(id=uuid4(), user_id=uuid4(), ts=base_time, text="桜道 珈琲話", tags=[]),
        Episode(id=uuid4(), user_id=uuid4(), ts=base_time, text="散歩道 明日会", tags=[]),
        Episode(id=uuid4(), user_id=uuid4(), ts=base_time, text="予備の4件目", tags=[]),
    ]

    highlights, wins, photos, quote_best = _summarise_episodes(episodes)

    assert highlights == {
        "count": 4,
        "entries": [
            "桜道 散歩道 朝会",
            "桜道 珈琲話",
            "散歩道 明日会",
        ],
    }
    assert wins["first_entry"] == "桜道 散歩道 朝会"
    assert wins["last_entry"] == "予備の4件目"
    assert "散歩道" in wins["keywords"]
    assert "桜道" in wins["keywords"]
    assert photos == {"sources": []}
    assert quote_best == "桜道 散歩道 朝会"
