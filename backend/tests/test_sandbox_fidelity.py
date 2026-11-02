"""The simulation must say exactly what the scenario says, and the scenario must fit its people."""
import copy
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from pipeline import sandbox_fidelity as fid  # noqa: E402
from pipeline import sandbox_geometry as sg  # noqa: E402

RAW = {
    "rooms": [{"id": "shop", "width_m": 8, "length_m": 6}, {"id": "store", "width_m": 6, "length_m": 5, "attach": {"to": "shop", "wall": "north", "align_frac": 0.2}}],
    "entry_points": [{"id": "front", "room": "shop", "wall": "south", "position_frac": 0.5, "width_m": 1.4, "state": "intact"},
                     {"id": "rear", "room": "store", "wall": "north", "position_frac": 0.5, "width_m": 1.6, "state": "forced"}],
    "connections": [{"id": "inner", "room_a": "shop", "room_b": "store", "position_frac": 0.5, "width_m": 1.0, "state": "open"}],
    "fixtures": [{"id": "till", "room": "shop", "position_frac": [0.5, 0.4], "footprint_m": [2, 0.7], "height_m": 1.0},
                 {"id": "safe", "room": "store", "position_frac": [0.5, 0.7], "footprint_m": [0.8, 0.6], "height_m": 1.0}],
}
LAY = sg.build_layout(RAW, set())
ACTORS = [{"id": "a", "label": "Thief", "role": "suspect"}, {"id": "v", "label": "Owner", "role": "victim"}]


def S(actor, node, action, dt=10, **kw):
    return {"actor": actor, "node_id": node, "action": action, "dt_sec_estimate": dt, "narrative": "", **kw}


STEPS = [S("a", "exterior", "approach"), S("a", "rear", "damage", item="crowbar", effects=[{"target": "rear", "state": "forced"}]),
         S("a", "till", "take_item", item="cash"), S("a", "exterior", "flee"), S("v", "till", "look")]


def plan_for(steps=STEPS, actors=ACTORS):
    return sg.plan_scenario(steps, LAY, actors)


EV = {"observations": [], "entities": [], "evidence_items": [], "conflicts": [], "relationships": [], "timeline": []}


def test_a_faithful_simulation_passes_the_round_trip():
    plan = plan_for()
    v, w, report = fid.round_trip(STEPS, ACTORS, plan, LAY)
    assert v == [] and report["round_trip_ok"] and report["steps_given"] == report["steps_in_simulation"] == 5
    assert report["effects_expected"] == report["effects_in_simulation"] == 1


def test_a_missing_step_is_caught():
    plan = plan_for()
    bad = copy.deepcopy(plan)
    bad["actors"][0]["steps"].pop(2)
    v, _, report = fid.round_trip(STEPS, ACTORS, bad, LAY)
    assert any(x["code"] == "fidelity_steps" for x in v) and not report["round_trip_ok"]


def test_a_changed_action_is_caught():
    bad = copy.deepcopy(plan_for())
    bad["actors"][0]["steps"][2]["action"] = "search"
    v, _, _ = fid.round_trip(STEPS, ACTORS, bad, LAY)
    assert any(x["code"] == "fidelity_steps" for x in v)


def test_a_stated_change_that_never_happens_is_caught():
    bad = copy.deepcopy(plan_for())
    bad["effects"] = []
    v, _, _ = fid.round_trip(STEPS, ACTORS, bad, LAY)
    assert any(x["code"] == "fidelity_effect" for x in v)


def test_an_item_nobody_mentioned_is_caught():
    bad = copy.deepcopy(plan_for())
    bad["actors"][0]["steps"][3]["item"] = "gold watch"
    v, _, _ = fid.round_trip(STEPS, ACTORS, bad, LAY)
    assert any(x["code"] == "fidelity_item" for x in v)


def test_a_person_with_no_steps_is_reported_not_silently_dropped():
    steps = [S("a", "exterior", "approach"), S("a", "till", "search")]
    plan = plan_for(steps)
    _, w, report = fid.round_trip(steps, ACTORS, plan, LAY)
    assert any("Owner is listed as a person" in x for x in w) and report["people_listed"] == 2 and report["people_shown"] == 1


def test_steps_the_planner_openly_dropped_are_not_blamed_on_the_software():
    steps = STEPS + [S("a", "no_such_place", "search")]
    plan = plan_for(steps)
    v, _, report = fid.round_trip(steps, ACTORS, plan, LAY)
    assert v == [] and report["steps_not_placed"] == 1


def test_summary_that_says_two_intruders_but_shows_one_is_flagged():
    plan = plan_for()
    assert fid.summary_count_warnings(["Two intruders forced the rear shutter."], plan)
    assert fid.summary_count_warnings(["One hooded intruder forced the rear shutter."], plan) == []
    assert fid.summary_count_warnings(["A single man entered."], plan) == []
    assert fid.summary_count_warnings(["The two doors were both forced."], plan) == []   # not about people


def test_summary_count_ignores_scenarios_with_no_suspect_listed():
    plan = plan_for(actors=[{"id": "a", "label": "Thief", "role": "other"}, {"id": "v", "label": "Owner", "role": "victim"}])
    assert fid.summary_count_warnings(["Two intruders came in."], plan) == []


def test_a_victim_who_takes_things_is_flagged_and_a_suspect_is_not():
    steps = [S("a", "exterior", "approach"), S("a", "till", "search"), S("v", "till", "take_item", item="cash"), S("v", "safe", "damage")]
    w = fid.role_warnings(plan_for(steps))
    assert len(w) == 2 and all("Owner" in x for x in w) and "list them as a suspect" in w[0]
    steps2 = [S("a", "till", "take_item", item="cash"), S("a", "safe", "damage")]
    assert fid.role_warnings(plan_for(steps2)) == []


def test_staff_and_witness_roles_are_checked_too_but_walking_and_looking_are_fine():
    actors = [{"id": "a", "label": "Thief", "role": "suspect"}, {"id": "s", "label": "Clerk", "role": "staff"}, {"id": "w", "label": "Neighbour", "role": "witness"}]
    steps = [S("a", "till", "search"), S("s", "till", "take_item", item="cash"), S("w", "exterior", "look"), S("w", "front", "move")]
    w = fid.role_warnings(plan_for(steps, actors))
    assert len(w) == 1 and "Clerk" in w[0] and "member of staff" in w[0]


def test_people_the_evidence_keeps_mentioning_must_appear_or_be_reported():
    ev = {**EV, "entities": [{"entity_id": "E1", "canonical_name": "Meena Rao", "entity_type": "person"}, {"entity_id": "E2", "canonical_name": "Thief", "entity_type": "person"}],
          "observations": [{"observation_id": f"OBS-{i}", "description": "Meena Rao said the shutter was open", "extracted_time": "01:00", "classification": "fact", "source_evidence_id": "EV-1"} for i in range(3)]}
    cov, w = fid.coverage(ev, plan_for(), ["A thief forced the rear door."], set())
    assert cov["people_not_covered"] == ["Meena Rao"] and any("Meena Rao" in x for x in w)
    cov2, w2 = fid.coverage(ev, plan_for(), ["Meena Rao arrived and found the till open."], set())
    assert cov2["people_not_covered"] == []


def test_a_name_that_is_only_mentioned_once_is_not_demanded():
    ev = {**EV, "entities": [{"entity_id": "E1", "canonical_name": "Meena Rao", "entity_type": "person"}],
          "observations": [{"observation_id": "OBS-1", "description": "Meena Rao locked up", "extracted_time": "01:00", "classification": "fact", "source_evidence_id": "EV-1"}]}
    cov, _ = fid.coverage(ev, plan_for(), ["A thief came in."], set())
    assert cov["people_not_covered"] == []


def test_low_use_of_the_most_relevant_observations_is_reported():
    obs = [{"observation_id": f"OBS-{i}", "description": f"event {i} at the shop", "extracted_time": f"01:{i:02d}", "classification": "fact", "source_evidence_id": "EV-1"} for i in range(12)]
    ev = {**EV, "observations": obs, "evidence_items": [{"evidence_id": "EV-1", "filename": "a.txt", "evidence_type": "text_document"}]}
    cov, w = fid.coverage(ev, plan_for(), ["A thief."], {"OBS-1"})
    assert cov["key_observations"] > 0 and cov["key_used"] == 1 and any("uses only 1 of the" in x for x in w)
    cov2, w2 = fid.coverage(ev, plan_for(), ["A thief."], {f"OBS-{i}" for i in range(12)})
    assert w2 == [] and cov2["key_used"] == cov2["key_observations"]


def test_check_combines_everything_and_names_the_caution_counts():
    out = fid.check(STEPS, ACTORS, plan_for(), LAY, EV, ["Two intruders broke in."], set())
    assert out["violations"] == [] and out["caution_counts"]["summary_count_mismatch"] == 1 and out["report"]["round_trip_ok"]


def test_generic_names_and_investigators_are_not_people_the_scenario_must_contain():
    obs_ = [{"observation_id": f"OBS-{i}", "description": "Several people and Inspector Karunakaran and the individuals were mentioned", "extracted_time": "01:00", "classification": "fact", "source_evidence_id": "EV-1"} for i in range(3)]
    ev = {**EV, "observations": obs_, "entities": [{"entity_id": "E1", "canonical_name": "several people", "entity_type": "person"},
                                                   {"entity_id": "E2", "canonical_name": "individuals", "entity_type": "person"},
                                                   {"entity_id": "E3", "canonical_name": "Inspector M. Karunakaran", "entity_type": "person"}]}
    cov, w = fid.coverage(ev, plan_for(), ["A thief."], set())
    assert cov["people_not_covered"] == []


def test_treating_a_named_person_from_the_evidence_as_a_suspect_is_flagged():
    ev = {**EV, "entities": [{"entity_id": "E1", "canonical_name": "Meena Rao", "entity_type": "person"}]}
    actors = [{"id": "a", "label": "Meena Rao", "role": "suspect"}, {"id": "b", "label": "Unknown man", "role": "suspect"}]
    w = fid.named_suspect_warnings(ev, plan_for([S("a", "till", "take_item", item="cash"), S("b", "safe", "search")], actors))
    assert len(w) == 1 and "Meena Rao" in w[0] and "points at them" in w[0]
    # the same person as a victim, or an unnamed suspect, is not flagged
    assert fid.named_suspect_warnings(ev, plan_for([S("a", "till", "look"), S("v", "safe", "search")], [{"id": "a", "label": "Meena Rao", "role": "victim"}, {"id": "v", "label": "x", "role": "suspect"}])) == []


def test_a_description_of_an_unidentified_person_is_not_treated_as_a_named_person():
    ev = {**EV, "entities": [{"entity_id": "E1", "canonical_name": "unidentified person in dark hooded windbreaker jacket", "entity_type": "person"},
                             {"entity_id": "E2", "canonical_name": "male individual", "entity_type": "person"}]}
    actors = [{"id": "a", "label": "unidentified person in dark hooded jacket", "role": "suspect"}]
    assert fid.named_suspect_warnings(ev, plan_for([S("a", "till", "take_item", item="cash"), S("a", "safe", "search")], actors)) == []
