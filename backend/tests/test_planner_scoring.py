import math

from app.config import SCORING_WEIGHTS
from app.services.planner import _hydrant_score, _sightline_penalty


def test_hydrant_score_breakdown_sums_to_score_and_is_normalized() -> None:
    score, breakdown = _hydrant_score(
        length_m=250.0,
        max_m=500.0,
        curvature=math.pi / 2,
        max_grade=0.075,
        hydrant_snap_m=10.0,
        max_snap_m=50.0,
    )
    assert set(breakdown) == {"length", "curvature", "grade", "snap"}
    assert score == round(sum(breakdown.values()), 4) or abs(score - sum(breakdown.values())) < 1e-9
    # length term = weight * (250/500) = 0.5 * weight
    assert breakdown["length"] == round(SCORING_WEIGHTS.length * 0.5, 4)
    # curvature term = weight * (pi/2 / pi) = 0.5 * weight
    assert breakdown["curvature"] == round(SCORING_WEIGHTS.curvature * 0.5, 4)


def test_hydrant_score_prefers_shorter_straighter_routes() -> None:
    short_straight, _ = _hydrant_score(100.0, 500.0, 0.0, 0.0, 5.0, 50.0)
    long_curvy, _ = _hydrant_score(450.0, 500.0, math.pi, 0.1, 40.0, 50.0)
    assert short_straight < long_curvy


def test_sightline_penalty_threshold_matches_caution_label() -> None:
    # A straight, flat edge is "good" (penalty 1.0, not > 1.5).
    assert _sightline_penalty({"curvature": 0.0, "grade": 0.0}) <= 1.5
    # A curvy, steep edge crosses the caution threshold.
    assert _sightline_penalty({"curvature": 0.01, "grade": 0.3}) > 1.5
