"""Offside checker: geometry against a synthetic camera with known ground truth, and detection decoding."""
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app import offside as of

W, D = of.BOXES["Penalty area"]


def camera(tilt: float = 0.0012, skew: float = 0.3, flip: bool = False) -> np.ndarray:
    """A pitch -> image homography with real perspective (pitch y = metres out from the goal line)."""
    G = np.array([[18.0, -6.0 * skew, 150.0],
                  [2.0 * skew, -14.0 if not flip else 14.0, 620.0 if not flip else 80.0],
                  [0.0, tilt, 1.0]])
    return G


def img_pt(G, x, y):
    q = G @ np.array([x, y, 1.0])
    return tuple(q[:2] / q[2])


def lines(G):
    far = (img_pt(G, 4, 16.5), img_pt(G, 36, 16.5))     # edge of the box
    near = (img_pt(G, 13, 5.5), img_pt(G, 27, 5.5))     # six-yard line
    return far, near


@pytest.mark.parametrize("G", [camera(), camera(0.004, 0.8), camera(0.0, 0.2), camera(0.002, 0.5, flip=True)],
                         ids=["tilted", "steep", "no-vanishing-point", "goal-at-top"])
def test_quick_verdicts_match_the_pitch(G):
    far, near = lines(G)
    dfd = img_pt(G, 15, 11.0)
    assert of.verdict(img_pt(G, 24, 10.0), dfd, far, near)["status"] == "offside"   # 1 m nearer the goal
    assert of.verdict(img_pt(G, 24, 12.0), dfd, far, near)["status"] == "onside"    # 1 m behind
    assert of.verdict(img_pt(G, 24, 11.0), dfd, far, near)["status"] == "level"     # level = onside
    assert of.verdict(img_pt(G, 30, 10.7), dfd, far, near)["status"] == "offside"   # 30 cm, far apart across the pitch


def test_depth_runs_from_far_line_to_near_line():
    G = camera()
    far, near = lines(G)
    assert of.depth(img_pt(G, 20, 16.5), far, near) == pytest.approx(0, abs=1e-6)
    assert of.depth(img_pt(G, 20, 5.5), far, near) == pytest.approx(1, abs=1e-6)
    assert of.depth(img_pt(G, 20, 2.0), far, near) > 1


@pytest.mark.parametrize("G", [camera(), camera(0.004, 0.8), camera(0.002, 0.5, flip=True)])
def test_precise_gap_in_centimetres(G):
    corners = [img_pt(G, 0, 0), img_pt(G, W, 0), img_pt(G, W, D), img_pt(G, 0, D)]
    H = of.box_homography(corners, "Penalty area")
    assert of.gap_cm(H, img_pt(G, 24, 10.66), img_pt(G, 15, 11.0)) == pytest.approx(34, abs=3)
    assert of.gap_cm(H, img_pt(G, 24, 12.0), img_pt(G, 15, 11.0)) == pytest.approx(-100, abs=3)
    # the vanishing point from the homography draws the same line as the quick clicks
    v1, v2 = of.vanishing_point_from_h(H), of.vanishing_point(*lines(G))
    assert abs(np.cross(v1, v2)).max() < 1e-6


def test_six_yard_box_works_too():
    G = camera()
    w6, d6 = of.BOXES["Six-yard box"]
    x0 = (W - w6) / 2
    corners = [img_pt(G, x0, 0), img_pt(G, x0 + w6, 0), img_pt(G, x0 + w6, d6), img_pt(G, x0, d6)]
    H = of.box_homography(corners, "Six-yard box")
    assert of.gap_cm(H, img_pt(G, 20, 7.0), img_pt(G, 25, 7.5)) == pytest.approx(50, abs=3)


def test_decode_and_nms_on_a_hand_built_output():
    raw = np.zeros((1, 8400, 85), np.float32)
    k = 20 * 80 + 10                          # stride-8 cell (10, 20)
    raw[0, k, :4] = [0.5, 0.5, np.log(4), np.log(8)]
    raw[0, k, 4], raw[0, k, 5] = 0.9, 0.8     # objectness x person = 0.72
    raw[0, k + 1, :4] = [-0.4, 0.5, np.log(4), np.log(8)]  # same player, next cell: suppressed
    raw[0, k + 1, 4], raw[0, k + 1, 5] = 0.8, 0.8
    raw[0, 100, 4], raw[0, 100, 6] = 0.9, 0.9  # a bicycle, not a person
    ps = of.people(raw, ratio=0.5)
    assert len(ps) == 1 and ps[0]["score"] == pytest.approx(0.72)
    x1, y1, x2, y2 = ps[0]["box"]
    assert (x1 + x2) / 2 == pytest.approx(10.5 * 8 / 0.5) and (y2 - y1) == pytest.approx(64 / 0.5)


def test_snap_picks_the_clicked_player():
    players = [{"box": (10, 10, 30, 60), "score": .9}, {"box": (100, 20, 120, 70), "score": .9}]
    assert of.snap((20, 30), players) == ((20.0, 60), 0)
    assert of.snap((112, 90), players) == ((110.0, 70), 1)          # just below his feet: nearest
    assert of.snap((400, 400), players) == ((400.0, 400.0), None)    # nobody near: the click itself


def test_annotate_draws_a_verdict():
    img = Image.new("RGB", (800, 500), (60, 140, 60))
    G = camera()
    far, near = lines(G)
    att, dfd = img_pt(G, 24, 10.0), img_pt(G, 15, 11.0)
    res = of.verdict(att, dfd, far, near)
    out = of.annotate(img, att=att, dfd=dfd, seg_far=far, seg_near=near, result=res, v=res["v"], credit="test")
    assert out.size == img.size and out.getpixel((40, 40)) != img.getpixel((40, 40))  # the sticker
    assert of.png_bytes(out)[:4] == b"\x89PNG"


@pytest.mark.skipif(not of.MODEL_PATH.exists(), reason="model not downloaded")
def test_detector_finds_the_players_in_the_demo():
    s = of.load_session(of.MODEL_PATH)
    img = Image.open(Path(of.ROOT) / "static" / "offside_demo.jpg")
    t0 = time.time()
    found = of.detect(s, img)
    assert len(found) >= 8
    assert time.time() - t0 < 5


def test_verdicts_become_fan_var_votes():
    assert of.vote_for("goal_overturned", "offside") == (True, None)
    assert of.vote_for("goal_overturned", "onside") == (False, "Goal")
    assert of.vote_for("goal_overturned", "level") == (False, "Goal")      # level = onside
    assert of.vote_for("goal_stands", "offside") == (False, "No goal")
    assert of.vote_for("goal_stands", "level") == (True, None)
    assert of.vote_for("penalty", "offside") is None
