"""Fan VAR vote store on a throwaway SQLite database (the live site uses Neon Postgres)."""
import pytest

from app import votes


@pytest.fixture()
def db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'fanvar.db'}"
    monkeypatch.setattr(votes, "_url", lambda: url)
    votes._engine.clear()
    votes._tally.clear()
    votes._flags.clear()
    yield votes.engine(url)
    votes._engine.clear()


def test_one_vote_per_device_and_revotes_update(db):
    votes.cast_vote("e1-100", "a" * 32, True, eng=db)
    votes.cast_vote("e1-100", "a" * 32, False, "No penalty", eng=db)   # changed mind
    votes.cast_vote("e1-100", "b" * 32, True, eng=db)
    s = votes.summary(["e1-100"]).loc["e1-100"]
    assert s.n == 2 and s.right == 1 and s.wrong_pct == 0.5 and s.top_alt == "No penalty"
    assert votes.my_votes("a" * 32, eng=db) == {"e1-100": (False, "No penalty")}


def test_fans_vs_neutrals_split(db):
    for i, (club, right) in enumerate([("Arsenal", False), ("Arsenal", False), ("Chelsea", True),
                                       (None, True), (None, False)]):
        votes.cast_vote("e2-5", f"{i:032x}", right, club=club, eng=db)
    s = votes.split("e2-5", "Arsenal", "Chelsea")
    assert s["Arsenal"] == (1.0, 2) and s["Chelsea"] == (0.0, 1) and s["neutrals"] == (0.5, 2)


def test_three_devices_promote_a_flag(db):
    for i in range(2):
        assert votes.flag("e3", 55, "Leeds", "Joe Rodon", "Penalty not given", f"{i:032x}", eng=db)
    assert votes.promoted_flags().empty
    assert not votes.flag("e3", 56, "Leeds", "Joe Rodon", "Penalty not given", f"{1:032x}", eng=db)  # same device again
    assert votes.promoted_flags().empty
    votes.flag("e3", 57, "Leeds", "Joe Rodon", "Penalty not given", f"{2:032x}", eng=db)
    p = votes.promoted_flags()
    assert len(p) == 1 and p.iloc[0]["n"] == 3 and p.iloc[0]["minute"] == 55
    with pytest.raises(ValueError):
        votes.flag("e3", 1, "Leeds", "X", "Free text isn't allowed", "c" * 32, eng=db)


def test_rate_limits(db, monkeypatch):
    monkeypatch.setattr(votes, "VOTES_PER_HOUR", 3)
    monkeypatch.setattr(votes, "FLAGS_PER_DAY", 2)
    for i in range(3):
        votes.cast_vote(f"e4-{i}", "d" * 32, True, eng=db)
    with pytest.raises(votes.RateLimited):
        votes.cast_vote("e4-9", "d" * 32, True, eng=db)
    votes.flag("e5", 10, "A", "P1", "Foul missed", "d" * 32, eng=db)
    votes.flag("e5", 10, "A", "P2", "Foul missed", "d" * 32, eng=db)
    with pytest.raises(votes.RateLimited):
        votes.flag("e5", 10, "A", "P3", "Foul missed", "d" * 32, eng=db)


def test_neon_urls_get_the_psycopg_driver(monkeypatch):
    monkeypatch.setattr(votes.st, "secrets", {"connections": {"fanvar": {"url": "postgresql://u:p@ep-x.neon.tech/db?sslmode=require"}}})
    assert votes._url().startswith("postgresql+psycopg://u:p@ep-x.neon.tech/db")
