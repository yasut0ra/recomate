import pytest


@pytest.fixture(autouse=True)
def isolated_bandit_state(tmp_path, monkeypatch):
    """Keep ChatEngine from reading or writing the real bandit state file."""
    path = tmp_path / "bandit_state.json"
    monkeypatch.setenv("RECOMATE_BANDIT_STATE_PATH", str(path))
    return path
