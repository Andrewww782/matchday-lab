import streamlit as st

from app import data, ui

st.title("Find a *player*")
st.markdown("Any player in Europe's top five leagues: see what he's worth, who plays like him, "
            "or put him head-to-head with someone else.")

if not data.available("players"):
    ui.missing("Player search")
    st.stop()

ui.player_search(key="find_player")
