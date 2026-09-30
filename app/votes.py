"""Fan VAR votes and flags: one vote per device per call, stored in Postgres (Neon) or SQLite.

The database URL comes from Streamlit secrets ([connections.fanvar] url = "postgresql://…"). Without
one (local development, tests, or before Neon is connected) votes go to a local SQLite file.

Fans are anonymous: each device gets a random id kept in an `fm_voter` cookie. That's enough to stop
casual double-voting; it isn't meant to stop someone determined, which is fine for a fan site."""
import datetime as dt
import re
import uuid

import pandas as pd
import sqlalchemy as sa
import streamlit as st

from app.data import DATA

LOCAL_DB = DATA / "build" / "fanvar.db"
VOTES_PER_HOUR = 120
FLAGS_PER_DAY = 10
FLAG_PROMOTE_AT = 3          # devices flagging the same moment before it becomes a votable call
CLAIMS = ["Penalty not given", "Should be a red card", "Should be a yellow card", "Foul missed",
          "Offside missed", "Handball missed"]

META = sa.MetaData()
VOTES = sa.Table(
    "votes", META,
    sa.Column("incident_id", sa.String(80), primary_key=True),
    sa.Column("voter", sa.String(32), primary_key=True),
    sa.Column("verdict", sa.SmallInteger, nullable=False),        # 1 = right call, 0 = wrong call
    sa.Column("should_be", sa.String(40)),
    sa.Column("supports", sa.String(60)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
FLAGS = sa.Table(
    "flags", META,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("event_id", sa.String(20), nullable=False),
    sa.Column("minute", sa.Integer, nullable=False),
    sa.Column("team", sa.String(60), nullable=False),
    sa.Column("player", sa.String(80), nullable=False),
    sa.Column("claim", sa.String(40), nullable=False),
    sa.Column("voter", sa.String(32), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("event_id", "player", "claim", "voter", name="one_flag_per_device"),
)


class RateLimited(Exception):
    pass


def _url() -> str:
    try:
        url = st.secrets["connections"]["fanvar"]["url"]
    except Exception:
        LOCAL_DB.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{LOCAL_DB}"
    # Neon hands out postgres:// or postgresql:// URLs; SQLAlchemy needs to be told to use psycopg 3.
    return re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", url)


@st.cache_resource(show_spinner=False)
def _engine(url: str) -> sa.Engine:
    eng = sa.create_engine(url, pool_pre_ping=True, pool_recycle=300)
    META.create_all(eng)
    return eng


def engine(url: str | None = None) -> sa.Engine:
    """One pooled engine per database URL (the cache is keyed on the URL, never on "whatever came first")."""
    return _engine(url or _url())


def backend() -> str:
    return engine().dialect.name  # "postgresql" or "sqlite"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _upsert(conn, table, row: dict, keys: list[str], update: list[str]):
    if conn.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    stmt = insert(table).values(**row)
    stmt = stmt.on_conflict_do_update(index_elements=keys, set_={c: stmt.excluded[c] for c in update}) if update \
        else stmt.on_conflict_do_nothing(index_elements=keys)
    conn.execute(stmt)


# ---------- the device id ----------

def voter_id() -> str:
    """This device's anonymous id: from the cookie if we've seen it before, otherwise a new one."""
    if "fm_voter" not in st.session_state:
        c = str(st.context.cookies.get("fm_voter") or "")
        if re.fullmatch(r"[0-9a-f]{32}", c):
            st.session_state["fm_voter"] = c
        else:
            st.session_state["fm_voter"] = uuid.uuid4().hex
            st.session_state["fm_cookie_pending"] = True
    return st.session_state["fm_voter"]


def supports() -> str | None:
    """The club this fan said they support (optional), remembered like the device id."""
    if "fm_club" not in st.session_state:
        st.session_state["fm_club"] = st.context.cookies.get("fm_club") or None
    return st.session_state["fm_club"]


def set_supports(club: str | None):
    st.session_state["fm_club"] = club
    st.session_state["fm_club_pending"] = True


def write_cookies():
    """Persist a new device id / club choice in the browser (runs once, from the footer)."""
    js = []
    if st.session_state.pop("fm_cookie_pending", False):
        js.append(f"document.cookie='fm_voter={voter_id()}; max-age=31536000; path=/; SameSite=Lax';")
    if st.session_state.pop("fm_club_pending", False):
        club = st.session_state.get("fm_club") or ""
        safe = re.sub(r"[^\w .'&-]", "", club)[:60]
        age = 31536000 if safe else 0
        js.append(f"document.cookie='fm_club={safe}; max-age={age}; path=/; SameSite=Lax';")
    if js:
        st.html("<script>" + "".join(js) + "</script>", unsafe_allow_javascript=True)


# ---------- votes ----------

def cast_vote(incident_id: str, voter: str, right: bool, should_be: str | None = None,
              club: str | None = None, eng: sa.Engine | None = None):
    eng = eng or engine()
    with eng.begin() as conn:
        recent = conn.execute(sa.select(sa.func.count()).select_from(VOTES).where(
            VOTES.c.voter == voter, VOTES.c.created_at >= _now() - dt.timedelta(hours=1))).scalar()
        if recent >= VOTES_PER_HOUR:
            raise RateLimited("That's a lot of calls in an hour. Take a breather and come back soon.")
        _upsert(conn, VOTES, {"incident_id": incident_id, "voter": voter, "verdict": int(bool(right)),
                              "should_be": should_be, "supports": club, "created_at": _now()},
                ["incident_id", "voter"], ["verdict", "should_be", "supports", "created_at"])
    _tally.clear()


@st.cache_data(ttl=30, show_spinner=False)
def _tally(ids: tuple[str, ...], url: str) -> pd.DataFrame:
    if not ids:
        return pd.DataFrame(columns=["incident_id", "supports", "verdict", "should_be", "n"])
    with engine(url).connect() as conn:
        q = (sa.select(VOTES.c.incident_id, VOTES.c.supports, VOTES.c.verdict, VOTES.c.should_be,
                       sa.func.count().label("n"))
             .where(VOTES.c.incident_id.in_(ids))
             .group_by(VOTES.c.incident_id, VOTES.c.supports, VOTES.c.verdict, VOTES.c.should_be))
        return pd.DataFrame(conn.execute(q).mappings().all(), columns=["incident_id", "supports", "verdict", "should_be", "n"])


def tally(ids) -> pd.DataFrame:
    """Raw vote counts per call, by the club the voter supports, verdict and suggested decision."""
    return _tally(tuple(sorted(set(ids))), _url())


def summary(ids) -> pd.DataFrame:
    """Per call: votes, share saying 'right call', and the most popular alternative."""
    t = tally(ids)
    if t.empty:
        return pd.DataFrame(columns=["n", "right", "wrong_pct", "top_alt"]).rename_axis("incident_id")
    g = t.groupby("incident_id")
    out = pd.DataFrame({"n": g["n"].sum(), "right": t[t.verdict == 1].groupby("incident_id")["n"].sum()}).fillna(0)
    out["wrong_pct"] = 1 - out["right"] / out["n"]
    alt = (t[(t.verdict == 0) & t.should_be.notna()].groupby(["incident_id", "should_be"])["n"].sum()
           .reset_index().sort_values("n", ascending=False).drop_duplicates("incident_id").set_index("incident_id"))
    out["top_alt"] = alt["should_be"]
    return out


def split(incident_id: str, home: str, away: str) -> dict:
    """Wrong-call share among each club's fans and among neutrals (None when nobody from a group voted)."""
    t = tally([incident_id])
    res = {}
    for label, mask in [(home, t.supports == home), (away, t.supports == away),
                        ("neutrals", ~t.supports.isin([home, away]))]:
        s = t[mask]
        n = int(s["n"].sum())
        res[label] = (1 - s.loc[s.verdict == 1, "n"].sum() / n, n) if n else (None, 0)
    return res


def my_votes(voter: str, eng: sa.Engine | None = None) -> dict:
    with (eng or engine()).connect() as conn:
        rows = conn.execute(sa.select(VOTES.c.incident_id, VOTES.c.verdict, VOTES.c.should_be)
                            .where(VOTES.c.voter == voter)).all()
    return {r.incident_id: (bool(r.verdict), r.should_be) for r in rows}


# ---------- flags ----------

def flag(event_id: str, minute: int, team: str, player: str, claim: str, voter: str,
         eng: sa.Engine | None = None) -> bool:
    """Flag a moment the ref missed. Returns False if this device already flagged it."""
    if claim not in CLAIMS:
        raise ValueError(claim)
    eng = eng or engine()
    with eng.begin() as conn:
        today = conn.execute(sa.select(sa.func.count()).select_from(FLAGS).where(
            FLAGS.c.voter == voter, FLAGS.c.created_at >= _now() - dt.timedelta(days=1))).scalar()
        if today >= FLAGS_PER_DAY:
            raise RateLimited("You've flagged 10 moments today. Thanks! Come back tomorrow for more.")
        before = conn.execute(sa.select(sa.func.count()).select_from(FLAGS).where(
            FLAGS.c.event_id == event_id, FLAGS.c.player == player, FLAGS.c.claim == claim,
            FLAGS.c.voter == voter)).scalar()
        _upsert(conn, FLAGS, {"event_id": event_id, "minute": int(minute), "team": team, "player": player,
                              "claim": claim, "voter": voter, "created_at": _now()},
                ["event_id", "player", "claim", "voter"], [])
    _flags.clear()
    return before == 0


@st.cache_data(ttl=30, show_spinner=False)
def _flags(url: str) -> pd.DataFrame:
    with engine(url).connect() as conn:
        q = (sa.select(FLAGS.c.event_id, FLAGS.c.team, FLAGS.c.player, FLAGS.c.claim,
                       sa.func.count(sa.distinct(FLAGS.c.voter)).label("n"),
                       sa.func.min(FLAGS.c.minute).label("minute"))
             .group_by(FLAGS.c.event_id, FLAGS.c.team, FLAGS.c.player, FLAGS.c.claim))
        return pd.DataFrame(conn.execute(q).mappings().all(),
                            columns=["event_id", "team", "player", "claim", "n", "minute"])


def flag_counts() -> pd.DataFrame:
    return _flags(_url())


def promoted_flags() -> pd.DataFrame:
    f = flag_counts()
    return f[f["n"] >= FLAG_PROMOTE_AT]
