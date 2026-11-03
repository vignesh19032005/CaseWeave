"""An alternative reading that sides with the other source of a disputed clock is scored down, not flattened to the floor; physics stays capped."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import sandbox_evidence as evd  # noqa: E402

STEPS = [{"strong_refs": [f"OBS-{i}"], "evidence_refs": [f"OBS-{i}"]} for i in range(6)]
OBS = {f"OBS-{i}" for i in range(6)}


def score(**kw):
    base = dict(llm_estimate=50, steps=STEPS, dropped=0, supporting=[], contradicted=[], hard_violations=0, observation_ids=OBS)
    base.update(kw)
    return evd.score_scenario(**base)


def test_without_any_problem_the_score_is_unchanged():
    assert score()["verifiable_score"] == 100


def test_a_clock_conflict_in_an_alternative_costs_eight_points_each_and_is_not_capped():
    one, two = score(soft_clock_conflicts=1), score(soft_clock_conflicts=2)
    assert one["verifiable_score"] == 92 and two["verifiable_score"] == 84
    assert one["cap_reason"] is None and one["components"]["alternative_clock_conflicts"] == 1


def test_those_conflicts_share_the_cap_of_thirty_points_with_other_contradictions():
    assert score(soft_clock_conflicts=10)["verifiable_score"] == 70


def test_a_hard_violation_still_caps_at_twenty_five_even_with_clock_conflicts():
    s = score(hard_violations=1, soft_clock_conflicts=1)
    assert s["verifiable_score"] == 25 and "capped at 25" in s["cap_reason"]


def test_the_formula_text_tells_the_reader_about_the_rule():
    assert "alternative reading" in evd.SCORE_FORMULA and "8 points" in evd.SCORE_FORMULA
