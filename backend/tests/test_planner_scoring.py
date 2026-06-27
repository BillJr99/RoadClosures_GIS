import math

from app.config import SCORING_WEIGHTS
from app.services.planner import _hydrant_score, _sightline_penalty, _within_radius_indices


def test_within_radius_indices_matches_linear_scan() -> None:
    xs = [0.0, 10.0, 100.0, 3.0]
    ys = [0.0, 0.0, 0.0, 4.0]
    # Points within 6 units of the origin: index 0 (0,0) and index 3 (3,4 -> dist 5).
    assert _within_radius_indices(xs, ys, 0.0, 0.0, 6.0) == [0, 3]
    assert _within_radius_indices([], [], 0.0, 0.0, 6.0) == []


def test_hydrant_score_breakdown_sums_to_score_and_is_normalized() -> None:
    score, breakdown = _hydrant_score(
        length_m=250.0,
        max_m=500.0,
        curvature=math.pi / 2,
        max_grade=0.075,
    )
    # The off-road snap gap is part of length_m, so it is not a separate term.
    assert set(breakdown) == {"length", "curvature", "grade"}
    assert score == round(sum(breakdown.values()), 4) or abs(score - sum(breakdown.values())) < 1e-9
    # length term = weight * (250/500) = 0.5 * weight
    assert breakdown["length"] == round(SCORING_WEIGHTS.length * 0.5, 4)
    # curvature term = weight * (pi/2 / pi) = 0.5 * weight
    assert breakdown["curvature"] == round(SCORING_WEIGHTS.curvature * 0.5, 4)


def test_hydrant_score_prefers_shorter_straighter_routes() -> None:
    short_straight, _ = _hydrant_score(100.0, 500.0, 0.0, 0.0)
    long_curvy, _ = _hydrant_score(450.0, 500.0, math.pi, 0.1)
    assert short_straight < long_curvy


def test_hydrant_score_prefers_longer_straight_over_shorter_sharp() -> None:
    # A farther but dead-straight hydrant should beat a closer one reached only
    # through sharp turns (curvature is weighted as heavily as length).
    longer_straight, _ = _hydrant_score(length_m=420.0, max_m=500.0, curvature=0.0, max_grade=0.0)
    shorter_curvy, _ = _hydrant_score(length_m=250.0, max_m=500.0, curvature=math.pi, max_grade=0.0)
    assert longer_straight < shorter_curvy


def test_sightline_penalty_threshold_matches_caution_label() -> None:
    # A straight, flat edge is "good" (penalty 1.0, not > 1.5).
    assert _sightline_penalty({"curvature": 0.0, "grade": 0.0}) <= 1.5
    # A curvy, steep edge crosses the caution threshold.
    assert _sightline_penalty({"curvature": 0.01, "grade": 0.3}) > 1.5
