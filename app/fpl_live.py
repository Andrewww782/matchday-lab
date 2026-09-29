"""Live look-ups against the public FPL API (a manager's squad). Everything else is precomputed."""
import requests
import streamlit as st

API = "https://fantasy.premierleague.com/api"
HEADERS = {"User-Agent": "Mozilla/5.0 (Matchday Lab)"}


class FplError(Exception):
    pass


@st.cache_data(ttl=900, show_spinner=False)
def squad(entry_id: int, gw: int) -> dict:
    try:
        r = requests.get(f"{API}/entry/{entry_id}/event/{gw}/picks/", headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        raise FplError("Couldn't reach the Fantasy Premier League site. Try again in a minute.") from e
    if r.status_code == 404:
        raise FplError("We couldn't find that team. Check the ID (it's the number in your Points page URL).")
    if not r.ok:
        raise FplError(f"The FPL site returned an error ({r.status_code}). Try again shortly.")
    js = r.json()
    try:
        name = requests.get(f"{API}/entry/{entry_id}/", headers=HEADERS, timeout=15).json().get("name")
    except (requests.RequestException, ValueError):
        name = None
    return {"picks": js.get("picks", []), "bank": js.get("entry_history", {}).get("bank", 0) / 10,
            "name": name}
