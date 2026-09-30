"""Fan VAR pieces: the incident card (vote → verdict), highlights, flags and the leaderboards."""
import html
import re
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st

from app import data, theme, ui, votes

KIND_LABEL = {
    "goal_overturned": ("VAR · Goal ruled out", "ink"), "goal_stands": ("VAR · Goal stands", "ink"),
    "var_penalty": ("VAR · Penalty given", "ink"), "var_no_penalty": ("VAR · No penalty", "ink"),
    "var_red": ("VAR · Red card", "ink"), "var_card_check": ("VAR · Card check", "ink"), "var_other": ("VAR", "ink"),
    "red": ("Red card", "red"), "penalty": ("Penalty", "lime"), "yellow": ("Yellow card", "lime"),
    "fan_flag": ("Fan flag", "red"),
}


def verdict(kind: str, wrong: float, n: int) -> str:
    """The crowd's verdict as a sticker line."""
    if n < 3:
        return "Early votes"
    pen = kind in ("penalty", "var_penalty")
    if wrong >= 0.75:
        return "Fans say: never a pen" if pen else "Fans say: howler"
    if wrong >= 0.6:
        return "Fans say: wrong call"
    if wrong > 0.4:
        return "Fans are split"
    if wrong > 0.25:
        return "Fans say: fair call"
    return "Fans say: stonewall pen" if pen else "Fans say: spot on"


def verdict_bar(right: float, n: int) -> str:
    r = round(100 * right)
    w = 100 - r

    def seg(pct, colour, text):
        t = text if pct >= 14 else (f"{pct}%" if pct >= 7 else "")
        return f'<div style="width:{pct}%;background:{colour};color:{theme.text_on(colour)}">{ui.num(t) if t else ""}</div>'

    return (f'<div class="ml-bar" style="height:40px">{seg(r, theme.LIME, f"Right call {r}%")}'
            f'{seg(w, theme.RED, f"Wrong call {w}%")}</div>'
            f'<div class="ml-legend"><span>{n} fan{"s" if n != 1 else ""} voted</span></div>')


def highlights(ev_row) -> None:
    """Official highlights, embedded when we found the video, otherwise a YouTube search."""
    vid = None
    if data.available("highlights"):
        h = data.table("highlights")
        hit = h[(h.event_id == ev_row["event_id"]) & h.video_id.notna()]
        vid = hit.video_id.iloc[0] if len(hit) else None
    with st.expander("▶ Watch the highlights"):
        q = quote_plus(f"{ev_row['home']} vs {ev_row['away']} highlights")
        search = f"https://www.youtube.com/results?search_query={q}"
        if vid:
            st.video(f"https://www.youtube.com/watch?v={vid}")
            st.caption("Official highlights on YouTube. Not every incident makes the highlights. "
                       f"Video not playing where you are? [Search YouTube instead]({search}).")
        else:
            st.link_button("Search the highlights on YouTube", search)
            st.caption("We couldn't match an official highlights video for this game yet.")


def _key(incident_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", incident_id)


def _my() -> dict:
    if "fm_my" not in st.session_state:
        st.session_state["fm_my"] = votes.my_votes(votes.voter_id())
    return st.session_state["fm_my"]


def _vote(incident_id: str, right: bool, should_be: str | None = None):
    try:
        votes.cast_vote(incident_id, votes.voter_id(), right, should_be, votes.supports())
    except votes.RateLimited as e:
        st.session_state[f"fm_err_{_key(incident_id)}"] = str(e)
        return
    _my()[incident_id] = (right, should_be)
    st.session_state.pop(f"fm_edit_{_key(incident_id)}", None)


@st.fragment
def card(inc: dict, compact: bool = False, scope: str = "big"):
    """One call: what happened, the highlights, your vote and what everyone else thinks.

    `scope` keeps widget keys unique when the same call shows in two places (e.g. two tabs)."""
    iid = inc["incident_id"]
    k = f"{scope}_{_key(iid)}"
    label, style = KIND_LABEL.get(inc["kind"], ("Call", "ink"))
    when = pd.Timestamp(inc["kickoff"]).tz_convert("Europe/London").strftime("%a %d %b")
    with st.container(border=True, key=f"fmcard_var_{k}"):
        st.html(ui.club_stripe(inc["home"], inc["away"])
                + '<div style="display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;margin-bottom:.35rem">'
                + ui.sticker(label, style, -2)
                + f'<span class="ml-muted">{html.escape(inc["minute"])} · {when}</span></div>'
                + f'<div class="fm-score">{ui.badge(inc["home"])}<span class="sc">{html.escape(inc["score"])}</span>'
                  f'{ui.badge(inc["away"])}</div>'
                + f'<div class="fm-call">{html.escape(inc["headline"])}</div>'
                + (f'<div class="ml-muted">Referee: {html.escape(str(inc["referee"]))}</div>'
                   if inc.get("referee") and str(inc.get("referee")) != "None" else ""))
        if not compact:
            with st.expander("What happened (match commentary)"):
                st.markdown("\n".join(f"- {html.escape(line)}" for line in str(inc["lines"]).split("\n")))
            highlights(inc)

        err = st.session_state.pop(f"fm_err_{_key(iid)}", None)
        if err:
            st.warning(err)
        mine = _my().get(iid)
        editing = st.session_state.get(f"fm_edit_{_key(iid)}")
        if mine is None or editing:
            question = "Did the ref get it right?" if inc["kind"] == "fan_flag" else "Was it the right call?"
            st.markdown(f"**{question}**")
            c1, c2 = st.columns(2)
            c1.button("✅ Right call", key=f"fm_r_{k}", on_click=_vote, args=(iid, True), width="stretch")
            c2.button("❌ Wrong call", key=f"fm_w_{k}", on_click=_vote, args=(iid, False), width="stretch")
            return

        s = votes.summary([iid])
        row = s.loc[iid] if iid in s.index else None
        n = int(row["n"]) if row is not None else 1
        right = float(row["right"] / row["n"]) if row is not None else float(mine[0])
        st.html(f'<div style="margin:.2rem 0 .4rem">{ui.sticker(verdict(inc["kind"], 1 - right, n), "ink", -2)}</div>'
                + verdict_bar(right, n))
        opts = [o for o in str(inc.get("options") or "").split("|") if o and o != inc.get("given")]
        if not mine[0] and opts:
            choice = st.segmented_control("What should it have been?", opts, key=f"fm_sb_{k}",
                                          default=mine[1] if mine[1] in opts else None)
            if choice and choice != mine[1]:
                _vote(iid, False, choice)
                st.rerun(scope="fragment")
        if row is not None and pd.notna(row.get("top_alt")) and n >= 3:
            st.caption(f"Fans who called it wrong mostly say: **{row['top_alt']}**.")
        sp = votes.split(iid, inc["home"], inc["away"])
        parts = [f"{grp} fans {w:.0%} wrong ({m})" if grp != "neutrals" else f"neutrals {w:.0%} wrong ({m})"
                 for grp, (w, m) in sp.items() if w is not None]
        if len(parts) >= 2:
            st.caption(" · ".join(parts))
        if st.button("Change my vote", key=f"fm_c_{k}", type="tertiary"):
            st.session_state[f"fm_edit_{_key(iid)}"] = True
            st.rerun(scope="fragment")


def flag_rows(matches: pd.DataFrame) -> list[dict]:
    """Moments flagged by enough fans become votable calls."""
    pf = votes.promoted_flags()
    out = []
    for f in pf.itertuples():
        m = matches[matches.event_id == f.event_id]
        if m.empty:
            continue
        m = m.iloc[0]
        slug = re.sub(r"[^a-z0-9]+", "-", f"{f.player}-{f.claim}".lower())
        out.append({"incident_id": f"flag-{f.event_id}-{slug}"[:80], "event_id": f.event_id, "league": m.league,
                    "gw": m.gw, "kickoff": m.kickoff, "home": m.home, "away": m.away, "score": m.score,
                    "minute": f"{int(f.minute)}'", "seconds": int(f.minute) * 60, "kind": "fan_flag", "big": True,
                    "headline": f"{f.claim}? {f.player} ({f.team}), flagged by {int(f.n)} fans",
                    "player": f.player, "against_team": f.team, "given": "", "options": "",
                    "lines": f"Fans flagged: {f.claim.lower()} involving {f.player} ({f.team}) around the {int(f.minute)}th minute.",
                    "referee": m.referee})
    return out


def flag_form(match: pd.Series):
    """Flag a moment the ref (and our feed) missed: fixed choices only, so nothing needs moderating."""
    lu = data.table("lineups") if data.available("lineups") else pd.DataFrame()
    lu = lu[lu.event_id == match["event_id"]] if len(lu) else lu
    with st.form(key=f"fm_flag_{match['event_id']}", border=True):
        st.markdown("**Did the ref miss something?** Flag it. When 3 fans flag the same moment, everyone gets to vote on it.")
        c1, c2 = st.columns(2)
        team = c1.selectbox("Team", [match["home"], match["away"]])
        minute = c2.number_input("Minute", 1, 130, 45)
        players = sorted(lu[lu.team == team].player) if len(lu) else []
        player = st.selectbox("Player involved", players or ["(line-up not available)"])
        claim = st.selectbox("What did the ref miss?", votes.CLAIMS)
        if st.form_submit_button("Flag it", type="primary"):
            if not players:
                st.warning("We don't have this game's line-up, so it can't be flagged yet.")
            else:
                try:
                    new = votes.flag(match["event_id"], int(minute), team, player, claim, votes.voter_id())
                    st.success("Flagged. Thanks!" if new else "You've already flagged that one.")
                except votes.RateLimited as e:
                    st.warning(str(e))


def controversy(summ: pd.DataFrame, inc: pd.DataFrame, min_votes: int = 3) -> pd.DataFrame:
    s = summ[summ["n"] >= min_votes].join(inc.set_index("incident_id")[["headline", "home", "away", "minute", "kind", "gw"]], how="inner")
    s["split"] = 1 - (s["wrong_pct"] - 0.5).abs() * 2
    return s


def referee_table(summ: pd.DataFrame, inc: pd.DataFrame, min_votes: int = 5, min_calls: int = 3) -> pd.DataFrame:
    s = summ[summ["n"] >= min_votes].join(inc.set_index("incident_id")[["referee"]], how="inner").dropna(subset=["referee"])
    s = s[s.referee.astype(str) != "None"]
    g = s.groupby("referee").agg(calls=("n", "size"), votes=("n", "sum"), agree=("wrong_pct", lambda w: 1 - w.mean()))
    return g[g["calls"] >= min_calls].sort_values("agree", ascending=False)


def robbed_table(summ: pd.DataFrame, inc: pd.DataFrame, min_votes: int = 5) -> pd.DataFrame:
    s = summ[summ["n"] >= min_votes].join(inc.set_index("incident_id")[["against_team", "benefit_team"]], how="inner")
    wrong = s[s["wrong_pct"] >= 0.5]
    against = wrong.groupby("against_team").size().rename("Wrong calls against")
    helped = wrong.groupby("benefit_team").size().rename("Wrong calls in their favour")
    t = pd.concat([against, helped], axis=1).fillna(0).astype(int)
    t["Net"] = t["Wrong calls against"] - t["Wrong calls in their favour"]
    return t.sort_values(["Net", "Wrong calls against"], ascending=False)
