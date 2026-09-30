"""Offside checker: geometry, player detection and drawing. No Streamlit here, so it's all testable.

The idea (the same one broadcasters use): lines on the pitch that run parallel to the goal line all meet
at one point in the picture, the *vanishing point*. A fan clicks two such lines (e.g. the six-yard line
and the goal line), we find where they meet, and every player's offside line is simply the line from
his feet to that point. Whose line is nearer the goal decides it: no camera calibration needed.

For centimetres we need real distances, so the optional precise step maps four clicked box corners onto
the real penalty area (40.32 m x 16.5 m) or six-yard box (18.32 m x 5.5 m) with a homography.

Players are found with YOLOX-S (Megvii, Apache-2.0) through onnxruntime on the CPU."""
import hashlib
import io
import math
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MODEL_URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx"
MODEL_SHA256 = "c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063"
MODEL_PATH = ROOT / "data" / "build" / "models" / "yolox_s.onnx"
INPUT = 640
BOXES = {"Penalty area": (40.32, 16.5), "Six-yard box": (18.32, 5.5)}
LEVEL_PX = 3.0      # lines closer than this at the attacker's feet count as level (level = onside)
LEVEL_CM = 5.0

INK, LIME, RED, BLUE, WHITE = (22, 22, 22), (200, 255, 46), (207, 43, 9), (40, 110, 230), (255, 255, 255)
FONT_DISPLAY = ROOT / "static" / "fonts" / "BowlbyOne-Regular.ttf"
FONT_BODY = ROOT / "static" / "fonts" / "DMSans.ttf"


# ---------- geometry (homogeneous coordinates) ----------

def _h(p) -> np.ndarray:
    return np.array([float(p[0]), float(p[1]), 1.0])


def line(p, q) -> np.ndarray:
    """The line through two image points."""
    return np.cross(_h(p), _h(q))


def intersect(l1, l2) -> np.ndarray:
    x = np.cross(l1, l2)
    return x[:2] / x[2]


def vanishing_point(seg_far, seg_near) -> np.ndarray:
    """Where two pitch lines parallel to the goal line meet in the picture (homogeneous: may be at infinity)."""
    v = np.cross(line(*seg_far), line(*seg_near))
    n = np.linalg.norm(v)
    return v / n if n else v


def offside_line(p, v) -> np.ndarray:
    """The line through a player's point and the vanishing point: his offside line in the picture."""
    return np.cross(_h(p), v)


def _mid(seg):
    return (np.asarray(seg[0], float) + np.asarray(seg[1], float)) / 2


def depth(p, seg_far, seg_near, v=None) -> float:
    """How far toward the goal a point is: 0 on the far line, 1 on the near line (beyond 1 = nearer still).

    Measured along the line joining the two clicked segments' midpoints. A perspective view keeps the
    order of points along a line, so comparing these numbers compares positions on the real pitch."""
    v = vanishing_point(seg_far, seg_near) if v is None else v
    a, b = _mid(seg_far), _mid(seg_near)
    q = intersect(offside_line(p, v), line(a, b))
    d = b - a
    return float(np.dot(q - a, d) / np.dot(d, d))


def verdict(att, dfd, seg_far, seg_near) -> dict:
    """OFFSIDE / ONSIDE / LEVEL for an attacker against the second-last defender."""
    v = vanishing_point(seg_far, seg_near)
    ta, td = depth(att, seg_far, seg_near, v), depth(dfd, seg_far, seg_near, v)
    ld = offside_line(dfd, v)
    gap_px = abs(float(ld @ _h(att))) / math.hypot(ld[0], ld[1])
    status = "level" if gap_px <= LEVEL_PX else ("offside" if ta > td else "onside")
    return {"status": status, "t_att": ta, "t_dfd": td, "gap_px": gap_px, "v": v}


def homography(img_pts, pitch_pts) -> np.ndarray:
    """4-point DLT: a 3x3 matrix taking image points to pitch coordinates (metres)."""
    rows = []
    for (x, y), (u, w) in zip(img_pts, pitch_pts):
        rows.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        rows.append([0, 0, 0, -x, -y, -1, w * x, w * y, w])
    _, _, vt = np.linalg.svd(np.asarray(rows, float))
    H = vt[-1].reshape(3, 3)
    return H / H[2, 2]


def to_pitch(H, p) -> np.ndarray:
    q = H @ _h(p)
    return q[:2] / q[2]


def box_homography(corners, box: str = "Penalty area") -> np.ndarray:
    """Corners clicked as: goal-line corner, the other goal-line corner, then the box-edge corner on that
    second side, then the box-edge corner on the first side. Pitch y = metres out from the goal line."""
    w, d = BOXES[box]
    return homography(corners, [(0, 0), (w, 0), (w, d), (0, d)])


def gap_cm(H, att, dfd) -> float:
    """Positive = the attacker is nearer the goal line than the defender (offside), in centimetres."""
    return float((to_pitch(H, dfd)[1] - to_pitch(H, att)[1]) * 100)


def vanishing_point_from_h(H) -> np.ndarray:
    """The image of the goal-line direction, so precise mode can draw lines without the quick clicks."""
    v = np.linalg.inv(H) @ np.array([1.0, 0.0, 0.0])
    return v / np.linalg.norm(v)


# ---------- player detection (YOLOX-S, ONNX) ----------

def ensure_model(path: Path = MODEL_PATH, url: str = MODEL_URL) -> Path:
    """Download the model once (36 MB) and check it. Raises if it can't."""
    if path.exists() and path.stat().st_size > 1_000_000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    if hashlib.sha256(tmp.read_bytes()).hexdigest() != MODEL_SHA256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("model download was corrupted")
    tmp.replace(path)
    return path


def load_session(path: Path | None = None):
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    return ort.InferenceSession(str(path or ensure_model()), opts, providers=["CPUExecutionProvider"])


def preprocess(img: Image.Image) -> tuple[np.ndarray, float]:
    """YOLOX input: letterboxed to 640x640 (top-left, grey padding), BGR, CHW, float32, no normalisation."""
    r = min(INPUT / img.height, INPUT / img.width)
    small = img.convert("RGB").resize((max(1, int(img.width * r)), max(1, int(img.height * r))), Image.BILINEAR)
    pad = np.full((INPUT, INPUT, 3), 114, np.float32)
    pad[:small.height, :small.width] = np.asarray(small, np.float32)
    return pad[:, :, ::-1].transpose(2, 0, 1)[None].copy(), r


def decode(out: np.ndarray) -> np.ndarray:
    """YOLOX raw head output (N, 8400, 85) -> boxes in input pixels (centre x, y, w, h, obj, classes...)."""
    grids, strides = [], []
    for s in (8, 16, 32):
        n = INPUT // s
        yv, xv = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        strides.append(np.full((n * n, 1), s))
    grid, stride = np.concatenate(grids), np.concatenate(strides)
    out = out.copy()
    out[..., :2] = (out[..., :2] + grid) * stride
    out[..., 2:4] = np.exp(out[..., 2:4]) * stride
    return out


def nms(boxes: np.ndarray, scores: np.ndarray, thr: float = 0.45) -> list[int]:
    x1, y1, x2, y2 = boxes.T
    area = (x2 - x1) * (y2 - y1)
    order, keep = scores.argsort()[::-1], []
    while order.size:
        i = order[0]
        keep.append(int(i))
        xx1, yy1 = np.maximum(x1[i], x1[order[1:]]), np.maximum(y1[i], y1[order[1:]])
        xx2, yy2 = np.minimum(x2[i], x2[order[1:]]), np.minimum(y2[i], y2[order[1:]])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        iou = inter / (area[i] + area[order[1:]] - inter + 1e-9)
        order = order[1:][iou <= thr]
    return keep


def people(raw: np.ndarray, ratio: float, score: float = 0.35) -> list[dict]:
    """People (COCO class 0) from a raw YOLOX output, in original-image pixels, left to right."""
    d = decode(raw)[0]
    conf = d[:, 4] * d[:, 5]
    m = conf >= score
    if not m.any():
        return []
    cx, cy, w, h = d[m, 0], d[m, 1], d[m, 2], d[m, 3]
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 1) / ratio
    keep = nms(boxes, conf[m])
    out = [{"box": tuple(float(v) for v in boxes[i]), "score": float(conf[m][i])} for i in keep]
    return sorted(out, key=lambda p: p["box"][0])


def detect(session, img: Image.Image, score: float = 0.35) -> list[dict]:
    arr, r = preprocess(img)
    raw = session.run(None, {session.get_inputs()[0].name: arr})[0]
    return people(raw, r, score)


def feet(box) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, y2)


def snap(click, players: list[dict], reach: float = 40.0):
    """The feet of the player that was clicked (or nearest), else the click itself."""
    x, y = click
    inside = [p for p in players if p["box"][0] - 6 <= x <= p["box"][2] + 6 and p["box"][1] - 6 <= y <= p["box"][3] + 6]
    if inside:
        best = min(inside, key=lambda p: (p["box"][2] - p["box"][0]) * (p["box"][3] - p["box"][1]))
        return feet(best["box"]), players.index(best)
    if players:
        i = min(range(len(players)), key=lambda k: math.dist(feet(players[k]["box"]), click))
        if math.dist(feet(players[i]["box"]), click) <= reach:
            return feet(players[i]["box"]), i
    return (float(x), float(y)), None


# ---------- drawing ----------

def _font(path: Path, size: int):
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def _clip_line(l, w, h):
    """Where an infinite image line crosses the picture's edges."""
    pts = []
    a, b, c = l
    for x in (0, w):
        if abs(b) > 1e-12:
            y = -(a * x + c) / b
            if 0 <= y <= h:
                pts.append((x, y))
    for y in (0, h):
        if abs(a) > 1e-12:
            x = -(b * y + c) / a
            if 0 <= x <= w:
                pts.append((x, y))
    pts = sorted(set((round(px, 2), round(py, 2)) for px, py in pts))
    return (pts[0], pts[-1]) if len(pts) >= 2 else None


def _half_plane(poly, l, keep_sign):
    """Clip a polygon to one side of a line (Sutherland-Hodgman, one edge)."""
    out = []
    val = [np.sign(l @ _h(p)) * keep_sign for p in poly]
    for i, p in enumerate(poly):
        q, vp, vq = poly[(i + 1) % len(poly)], val[i], val[(i + 1) % len(poly)]
        if vp >= 0:
            out.append(p)
        if vp * vq < 0:
            out.append(tuple(intersect(line(p, q), l)))
    return out


def annotate(img: Image.Image, players=(), att=None, dfd=None, att_i=None, dfd_i=None, seg_far=None,
             seg_near=None, pending=(), result=None, v=None, credit: str | None = None) -> Image.Image:
    """The picture with boxes, clicks, both offside lines, the offside zone and the verdict sticker."""
    im = img.convert("RGB").copy()
    w, h = im.size
    s = max(1.0, w / 1000)                                   # scale line widths and text with the picture
    over = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    small = _font(FONT_BODY, int(15 * s))
    for k, p in enumerate(players):
        colour = BLUE if k == att_i else RED if k == dfd_i else LIME
        width = int(3 * s) if k in (att_i, dfd_i) else max(1, int(1.5 * s))
        d.rectangle(p["box"], outline=colour + (255,), width=width)
        tx, ty = p["box"][0], p["box"][1] - 18 * s
        d.rectangle((tx, ty, tx + 22 * s, ty + 17 * s), fill=INK + (220,))
        d.text((tx + 4 * s, ty), str(k + 1), fill=LIME + (255,), font=small)

    if v is not None and dfd is not None:
        ld = offside_line(dfd, v)
        seg = _clip_line(ld, w, h)
        if seg and result is not None and seg_near is not None:
            goal_side = np.sign(ld @ _h(_mid(seg_near))) or 1.0
            zone = _half_plane([(0, 0), (w, 0), (w, h), (0, h)], ld, goal_side)
            if len(zone) >= 3:
                d.polygon(zone, fill=RED + (72,))
        if seg:
            d.line(seg, fill=RED + (255,), width=int(4 * s))
    if v is not None and att is not None:
        seg = _clip_line(offside_line(att, v), w, h)
        if seg:
            d.line(seg, fill=BLUE + (255,), width=int(3 * s))
    for sg in (seg_far, seg_near):
        if sg:
            d.line(sg, fill=WHITE + (255,), width=int(3 * s))
            d.line(sg, fill=INK + (255,), width=max(1, int(1 * s)))
    for p in list(pending) + [x for sg in (seg_far, seg_near) if sg for x in sg]:
        r = 6 * s
        d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=LIME + (255,), outline=INK + (255,), width=int(2 * s))
    for p, colour in ((att, BLUE), (dfd, RED)):
        if p is not None:
            r = 8 * s
            d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=colour + (255,), outline=WHITE + (255,), width=int(2 * s))

    if result is not None:
        label = {"offside": "OFFSIDE", "onside": "ONSIDE", "level": "LEVEL: ONSIDE"}[result["status"]]
        big = _font(FONT_DISPLAY, int(40 * s))
        bw, bh = d.textbbox((0, 0), label, font=big)[2:]
        x0, y0 = 20 * s, 20 * s
        fill, text = (RED, WHITE) if result["status"] == "offside" else (LIME, INK)
        d.rounded_rectangle((x0 - 4 * s, y0 - 4 * s, x0 + bw + 36 * s, y0 + bh + 28 * s), 14 * s, fill=INK + (255,))
        d.rounded_rectangle((x0, y0, x0 + bw + 28 * s, y0 + bh + 20 * s), 12 * s, fill=fill + (255,))
        d.text((x0 + 14 * s, y0 + 6 * s), label, fill=text + (255,), font=big)
    mark = "FOOTYMINDS · offside check" + (f"   {credit}" if credit else "")
    tw, th = d.textbbox((0, 0), mark, font=small)[2:]
    d.rectangle((w - tw - 16 * s, h - th - 12 * s, w, h), fill=INK + (200,))
    d.text((w - tw - 8 * s, h - th - 8 * s), mark, fill=LIME + (255,), font=small)
    return Image.alpha_composite(im.convert("RGBA"), over).convert("RGB")


def png_bytes(img: Image.Image) -> bytes:
    b = io.BytesIO()
    img.save(b, format="PNG", optimize=True)
    return b.getvalue()


# ---------- the precise views ----------

def pitch_map_fig(H, att, dfd, box: str):
    """Top-down map of the box with both players and the offside line."""
    import plotly.graph_objects as go
    w, dd = BOXES[box]
    a, b = to_pitch(H, att), to_pitch(H, dfd)
    fig = go.Figure()
    fig.add_shape(type="rect", x0=-8, y0=0, x1=w + 8, y1=max(dd, a[1], b[1]) + 6, fillcolor="#3E8E41", line_width=0, layer="below")
    fig.add_shape(type="rect", x0=0, y0=0, x1=w, y1=dd, line=dict(color="white", width=3))
    fig.add_shape(type="line", x0=-8, y0=0, x1=w + 8, y1=0, line=dict(color="white", width=3))
    fig.add_shape(type="line", x0=-8, y0=b[1], x1=w + 8, y1=b[1], line=dict(color="#CF2B09", width=3, dash="dash"))
    fig.add_trace(go.Scatter(x=[b[0]], y=[b[1]], mode="markers+text", text=["Defender"], textposition="middle left",
                             marker=dict(size=16, color="#CF2B09", line=dict(color="white", width=2)), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=[a[0]], y=[a[1]], mode="markers+text", text=["Attacker"], textposition="middle right",
                             marker=dict(size=16, color="#286EE6", line=dict(color="white", width=2)), hoverinfo="skip"))
    fig.update_xaxes(visible=False, range=[-8, w + 8])
    fig.update_yaxes(visible=False, scaleanchor="x", range=[max(dd, a[1], b[1]) + 6, -3])
    fig.update_layout(showlegend=False, height=360, margin=dict(l=0, r=0, t=0, b=0),
                      font=dict(color="white", family="DM Sans, sans-serif"))
    return fig


def var_3d_fig(H, att, dfd, box: str):
    """The broadcast-style 3D view: a close-up of the pitch around the two players, the pink vertical offside
    plane through the defender, both players, and an arrow toward goal. Heights are exaggerated so the
    plane reads as a wall, and the camera looks at the goal from behind the wall."""
    import plotly.graph_objects as go
    a, b = to_pitch(H, att), to_pitch(H, dfd)
    x0, x1 = min(a[0], b[0]) - 9, max(a[0], b[0]) + 9
    y0, y1 = min(a[1], b[1]) - 6, max(a[1], b[1]) + 6
    zt = 3.0
    fig = go.Figure()
    fig.add_trace(go.Mesh3d(x=[x0, x1, x1, x0], y=[y0, y0, y1, y1], z=[0, 0, 0, 0], i=[0, 0], j=[1, 2], k=[2, 3],
                            color="#3E8E41", opacity=1, flatshading=True, hoverinfo="skip"))
    for yy in np.arange(np.ceil(y0), y1, 2.0):   # mowing stripes, like a real pitch
        fig.add_trace(go.Mesh3d(x=[x0, x1, x1, x0], y=[yy, yy, yy + 1, yy + 1], z=[0.01] * 4, i=[0, 0], j=[1, 2], k=[2, 3],
                                color="#46A04A", opacity=1, flatshading=True, hoverinfo="skip"))
    fig.add_trace(go.Mesh3d(x=[x0, x1, x1, x0], y=[b[1]] * 4, z=[0, 0, 2.2, 2.2], i=[0, 0], j=[1, 2], k=[2, 3],
                            color="#FF6FA8", opacity=0.55, flatshading=True, hoverinfo="skip"))
    fig.add_trace(go.Scatter3d(x=[x0, x1], y=[b[1], b[1]], z=[0.03, 0.03], mode="lines",
                               line=dict(color="#CF2B09", width=6), hoverinfo="skip"))
    for p, colour, name in ((a, "#286EE6", "Attacker"), (b, "#CF2B09", "Defender")):
        fig.add_trace(go.Scatter3d(x=[p[0], p[0]], y=[p[1], p[1]], z=[0, 1.55], mode="lines",
                                   line=dict(color=colour, width=18), hoverinfo="skip"))
        fig.add_trace(go.Scatter3d(x=[p[0]], y=[p[1]], z=[1.8], mode="markers+text", text=[name], textposition="top center",
                                   marker=dict(size=9, color=colour), textfont=dict(size=13, color="#161616"),
                                   hoverinfo="skip"))
    gx = (x0 + x1) / 2
    fig.add_trace(go.Cone(x=[gx], y=[b[1] + 0.5], z=[2.7], u=[0], v=[-2.5], w=[0], sizeref=1.4, anchor="tail",
                          colorscale=[[0, "#C8FF2E"], [1, "#C8FF2E"]], showscale=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter3d(x=[gx], y=[b[1] + 1.5], z=[2.95], mode="text", text=["Goal direction"],
                               textfont=dict(size=14, color="#161616"), hoverinfo="skip"))
    dx, dy = x1 - x0, y1 - y0
    fig.update_layout(scene=dict(xaxis=dict(visible=False, range=[x0, x1]), yaxis=dict(visible=False, range=[y0, y1]),
                                 zaxis=dict(visible=False, range=[0, zt]), aspectmode="manual",
                                 aspectratio=dict(x=1, y=dy / dx, z=zt / dx * 3.5),
                                 camera=dict(eye=dict(x=1.15, y=0.95, z=0.5), center=dict(x=0, y=0, z=-0.1))),
                      showlegend=False, height=420, margin=dict(l=0, r=0, t=0, b=0),
                      paper_bgcolor="#EAF4FF", font=dict(color="#161616", family="DM Sans, sans-serif"))
    return fig


# ---------- Fan VAR ----------

def vote_for(kind: str, status: str) -> tuple[bool, str | None] | None:
    """Turn an offside verdict into a vote on a Fan VAR call: (right call?, what it should have been)."""
    off = status == "offside"                       # level counts as onside
    if kind == "goal_overturned":                   # the ref said no goal
        return (True, None) if off else (False, "Goal")
    if kind == "goal_stands":                       # the ref said goal
        return (False, "No goal") if off else (True, None)
    return None
