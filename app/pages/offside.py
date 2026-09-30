import hashlib
import html
import io
import tempfile
from pathlib import Path

import streamlit as st
from PIL import Image
from streamlit_image_coordinates import streamlit_image_coordinates

from app import data, offside as of, ui, var_ui, votes

PAGES = st.session_state["pages"]
DEMO = Path(of.ROOT) / "static" / "offside_demo.jpg"
DEMO_CREDIT = "Photo: Roger Cornfoot, CC BY-SA 2.0"
MAX_W = 1400


@st.cache_resource(show_spinner="Warming up the player spotter (first time only)…")
def _session():
    try:
        return of.load_session()
    except Exception:
        try:  # the app folder may be read-only on some hosts
            path = Path(tempfile.gettempdir()) / "footyminds" / "yolox_s.onnx"
            return of.load_session(of.ensure_model(path))
        except Exception:
            return None


@st.cache_data(max_entries=24, show_spinner="Spotting the players…")
def _players(digest: str, raw: bytes) -> list[dict]:
    s = _session()
    return of.detect(s, Image.open(io.BytesIO(raw))) if s is not None else []


def _load(raw: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    if img.width > MAX_W:
        img = img.resize((MAX_W, round(img.height * MAX_W / img.width)), Image.LANCZOS)
    return img


def _jpeg(img: Image.Image) -> bytes:
    b = io.BytesIO()
    img.save(b, format="JPEG", quality=92)
    return b.getvalue()


# ---- which call are we checking? (opened from a Fan VAR card) ----
call = None
cid = st.query_params.get("call")
if cid and data.available("incidents"):
    inc = data.table("incidents")
    hit = inc[inc.incident_id == cid]
    call = hit.iloc[0].to_dict() if len(hit) else None

ui.hero("Was it <em>offside?</em>",
        "Draw the lines yourself, like VAR does: pick the attacker and the last defender, show us the "
        "pitch's perspective, and get the verdict.", tag="Offside check")

if call:
    with st.container(border=True, key="fmcard_ofs_call"):
        st.html(ui.club_stripe(call["home"], call["away"])
                + ui.sticker(var_ui.KIND_LABEL.get(call["kind"], ("Call", "ink"))[0], "ink", -2)
                + f'<div class="fm-score" style="margin-top:.4rem">{ui.badge(call["home"])}'
                  f'<span class="sc">{html.escape(call["score"])}</span>{ui.badge(call["away"])}</div>'
                + f'<div class="fm-call">{html.escape(call["headline"])} · {html.escape(call["minute"])}</div>')
        var_ui.highlights(call)
        st.caption("Pause the highlights at the moment the ball is played, take a screenshot, and upload it below.")

# ---- step 1: the picture ----
ui.eyebrow("Step 1")
st.subheader("Your picture")
src = st.segmented_control("Picture", ["Upload a screenshot", "Try the demo"], required=True,
                           default="Try the demo" if not call else "Upload a screenshot", key="ofs_src",
                           label_visibility="collapsed")
raw, credit = None, None
if src == "Upload a screenshot":
    up = st.file_uploader("A screenshot of the moment the ball is played (PNG or JPG, up to 8 MB)",
                          type=["png", "jpg", "jpeg", "webp"], key="ofs_upload")
    if up is not None:
        if up.size > 8 * 1024 * 1024:
            st.warning("That picture is over 8 MB. A normal screenshot is plenty.")
        else:
            raw = up.getvalue()
    st.caption("Your picture is only used for this check. It isn't saved or shared.")
else:
    raw, credit = DEMO.read_bytes(), DEMO_CREDIT
    st.caption(f"Demo: a non-league match in England. {DEMO_CREDIT}, via Wikimedia Commons.")
if raw is None:
    st.stop()

img = _load(raw)
raw_small = _jpeg(img)
digest = hashlib.sha1(raw_small).hexdigest()[:16]
players = _players(digest, raw_small)

S = st.session_state.setdefault("ofs", {})
if S.get("key") != digest:
    S.clear()
    S.update(key=digest, att=None, dfd=None, att_i=None, dfd_i=None, pts=[], corners=[], seen=set())


def stage() -> str:
    if S["att"] is None:
        return "attacker"
    if S["dfd"] is None:
        return "defender"
    if len(S["pts"]) < 4:
        return "lines"
    return "verdict"


def undo():
    if S["pts"]:
        S["pts"].pop()
    elif S["dfd"] is not None:
        S["dfd"], S["dfd_i"] = None, None
    elif S["att"] is not None:
        S["att"], S["att_i"] = None, None


def restart():
    S.update(att=None, dfd=None, att_i=None, dfd_i=None, pts=[], corners=[])


now = stage()
seg_far = tuple(S["pts"][:2]) if len(S["pts"]) >= 2 else None
seg_near = tuple(S["pts"][2:4]) if len(S["pts"]) >= 4 else None
pending = S["pts"][len(S["pts"]) // 2 * 2:] if now == "lines" else []
result = of.verdict(S["att"], S["dfd"], seg_far, seg_near) if now == "verdict" else None

# ---- steps 2-3: clicks on the picture ----
STEPS = {
    "attacker": ("Step 2", "Click the attacker", "The player who might be offside. Click on him; we'll use his feet."),
    "defender": ("Step 2", "Now the second-last defender", "Usually the last outfield defender (the keeper is normally the last man)."),
    "lines": ("Step 3", "Show us the perspective",
              ["Click two points along a pitch line that runs parallel to the goal line, e.g. the edge of the box.",
               "…and the second point on that line.",
               "Now two points on another line parallel to the goal line, nearer the goal (six-yard line or goal line).",
               "…and the last point."][len(S["pts"])] if len(S["pts"]) < 4 else ""),
    "verdict": ("Step 4", "The verdict", ""),
}
num, title, tip = STEPS[now]
ui.eyebrow(num)
st.subheader(title)
if tip:
    st.caption(tip)
if not players and now in ("attacker", "defender"):
    st.info("We couldn't spot the players automatically, so click exactly where each player's feet are.")

c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="center")
exact = c1.toggle("Use my exact click", key="ofs_exact",
                  help="Place the point yourself (e.g. a leading foot) instead of snapping to the detected player.")
c2.button("↶ Undo", on_click=undo, width="stretch", disabled=now == "attacker")
c3.button("Start over", on_click=restart, width="stretch", disabled=now == "attacker")

shown = of.annotate(img, players, S["att"], S["dfd"], S["att_i"], S["dfd_i"], seg_far, seg_near, pending,
                    result, result["v"] if result else (of.vanishing_point(seg_far, seg_near) if seg_near else None),
                    credit)
click = streamlit_image_coordinates(shown, key=f"ofs_click_{digest}_{now}_{len(S['pts'])}", use_column_width="always",
                                    image_format="JPEG", jpeg_quality=88, cursor="crosshair")
if click and click.get("unix_time") not in S["seen"] and now != "verdict":
    S["seen"].add(click.get("unix_time"))
    k = img.width / click["width"]
    p = (click["x"] * k, click["y"] * k)
    if now in ("attacker", "defender"):
        pt, idx = (p, None) if exact else of.snap(p, players, reach=40 * k)
        if now == "attacker":
            S["att"], S["att_i"] = pt, idx
        else:
            S["dfd"], S["dfd_i"] = pt, idx
    else:
        S["pts"].append(p)
    st.rerun()

# ---- step 4: the verdict ----
if result:
    label = {"offside": ("Offside", "red"), "onside": ("Onside", "lime"), "level": ("Level: onside", "lime")}[result["status"]]
    st.html(f'<div style="margin:.4rem 0 .2rem">{ui.sticker(label[0], label[1], -3)}</div>')
    if result["status"] == "level":
        st.markdown("The two lines are too close to separate on this picture, and **level counts as onside**.")
    elif result["status"] == "offside":
        st.markdown("The attacker's line (blue) is **nearer the goal** than the defender's (red): offside.")
    else:
        st.markdown("The attacker's line (blue) is **behind** the defender's (red): onside.")
    st.caption("We compare the players' feet in the frame you chose. Real offside uses any part of the body you "
               "can score with (not the arms), at the exact moment the ball is played, and only counts in the "
               "opponents' half.")
    a, b = st.columns(2)
    a.download_button("⬇ Download the picture", of.png_bytes(shown), file_name="footyminds-offside.png",
                      mime="image/png", width="stretch")
    if call:
        v = of.vote_for(call["kind"], result["status"])
        if v and b.button("Save as my vote on this call", type="primary", width="stretch"):
            try:
                votes.cast_vote(call["incident_id"], votes.voter_id(), v[0], v[1], votes.supports())
                st.session_state.setdefault("fm_my", {})[call["incident_id"]] = v
                st.success("Saved. " + ("You called it the right call." if v[0] else "You called it a wrong call."))
            except votes.RateLimited as e:
                st.warning(str(e))
        b.page_link(PAGES["var"], label="Back to Fan VAR", icon=":material/sports:")

    with st.expander("📏 Measure the gap (optional): click the 4 corners of a box"):
        box = st.segmented_control("Which box can you see?", list(of.BOXES), default="Penalty area",
                                   required=True, key="ofs_box")
        n = len(S["corners"])
        order = ["a corner of the box on the goal line", "the other goal-line corner",
                 "the box-edge corner on that same side", "the last box-edge corner"]
        if n < 4:
            st.caption(f"Click {order[n]} ({n + 1} of 4). Corners can be off the picture's edge only if you can "
                       "still see where they are.")
        else:
            if st.button("Redo the corners"):
                S["corners"] = []
                st.rerun()
        pic = of.annotate(img, (), S["att"], S["dfd"], None, None, None, None, S["corners"], None, None, credit)
        cc = streamlit_image_coordinates(pic, key=f"ofs_corner_{digest}_{n}_{box}", use_column_width="always",
                                         image_format="JPEG", jpeg_quality=85, cursor="crosshair")
        if cc and cc.get("unix_time") not in S["seen"] and n < 4:
            S["seen"].add(cc.get("unix_time"))
            k = img.width / cc["width"]
            S["corners"].append((cc["x"] * k, cc["y"] * k))
            st.rerun()
        if n == 4:
            H = of.box_homography(S["corners"], box)
            g = of.gap_cm(H, S["att"], S["dfd"])
            if abs(g) > 3000:
                st.warning("Those corners don't look like a box from this angle. Try again, in the order shown.")
            else:
                word = "Level" if abs(g) < of.LEVEL_CM else ("Offside by" if g > 0 else "Onside by")
                st.html(f'<div class="fm-call">{word}{"" if word == "Level" else f" {abs(g):.0f} cm"}</div>')
                m1, m2 = st.columns([2, 3])
                with m1:
                    st.caption("From above")
                    st.plotly_chart(of.pitch_map_fig(H, S["att"], S["dfd"], box), width="stretch",
                                    config={"displayModeBar": False})
                with m2:
                    st.caption("The VAR view (drag to turn it)")
                    st.plotly_chart(of.var_3d_fig(H, S["att"], S["dfd"], box), width="stretch",
                                    config={"displayModeBar": False})
                st.caption("Centimetres depend on how exactly the corners and feet are clicked: treat anything "
                           "under ~20 cm as too close to call.")

ui.how_it_works("""
- Lines on the pitch that run **parallel to the goal line** (the edge of the box, the six-yard line, the goal
  line) all meet at one point in a camera picture, far off to one side. Your four clicks tell us where.
- Each player's **offside line** is the line from his feet to that point, which is exactly how broadcasters draw them.
  Whichever line is nearer the goal wins.
- **Measure the gap** maps four box corners onto the real box (40.32 m × 16.5 m, or 18.32 m × 5.5 m for the
  six-yard box) to turn the gap into centimetres and build the top-down and 3D views.
- Players are spotted automatically by **YOLOX** (an open-source detector, Apache-2.0) running on our server.
  Your picture is never stored.
""")
