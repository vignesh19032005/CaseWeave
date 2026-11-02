"""Scenarios must be genuinely different possibilities, found by code from what the evidence leaves open."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from pipeline import sandbox_diversity as dv  # noqa: E402
from pipeline import sandbox_geometry as sg  # noqa: E402

RAW = {
    "rooms": [{"id": "shop", "width_m": 8, "length_m": 6}, {"id": "store", "width_m": 6, "length_m": 5, "attach": {"to": "shop", "wall": "north", "align_frac": 0.2}}],
    "entry_points": [{"id": "front", "label": "Front door", "room": "shop", "wall": "south", "position_frac": 0.5, "width_m": 1.4, "state": "intact", "basis": "stated"},
                     {"id": "rear", "label": "Rear shutter", "room": "store", "wall": "north", "position_frac": 0.5, "width_m": 1.6, "state": "forced", "basis": "stated"}],
    "connections": [{"id": "inner", "room_a": "shop", "room_b": "store", "position_frac": 0.5, "width_m": 1.0, "state": "open"}],
    "fixtures": [{"id": "till", "room": "shop", "position_frac": [0.5, 0.4], "footprint_m": [2, 0.7], "height_m": 1.0},
                 {"id": "safe", "room": "store", "position_frac": [0.5, 0.7], "footprint_m": [0.8, 0.6], "height_m": 1.0}],
}
LAY = sg.build_layout(RAW, set())
ACT = [{"id": "a", "label": "Thief", "role": "suspect"}, {"id": "b", "label": "Second", "role": "suspect"}]


def obs(*texts):
    return {"observations": [{"observation_id": f"OBS-{i}", "description": t} for i, t in enumerate(texts)], "conflicts": [], "entities": []}


def S(actor, node, action, dt=10, **kw):
    return {"actor": actor, "node_id": node, "action": action, "dt_sec_estimate": dt, "narrative": "", **kw}


def scn(steps, actors=None):
    plan = sg.plan_scenario(steps, LAY, actors or ACT[:1])
    return {"plan": plan, "time": {"clock_anchors": []}, "scenario_id": "S"}


# ---------------------------------------------------------------- open questions

def test_entry_is_an_open_question_when_there_are_two_outside_doors_and_the_forced_one_is_best_supported():
    axes = dv.open_questions(LAY, obs("The shop was broken into."))
    entry = next(a for a in axes if a["key"] == "entry")
    assert entry["options"][0]["id"] == "rear" and entry["options"][0]["support"] == "best"
    assert entry["options"][1]["id"] == "front" and entry["options"][1]["support"] == "alternative"


def test_no_entry_question_with_a_single_outside_door():
    lay = sg.build_layout({**RAW, "entry_points": RAW["entry_points"][:1]}, set())
    assert not any(a["key"] == "entry" for a in dv.open_questions(lay, obs("x")))


def test_people_count_is_offered_only_when_the_evidence_points_both_ways():
    only_one = dv.open_questions(LAY, obs("A lone man was seen on the camera.", "He worked alone."))
    assert not any(a["key"] == "people" for a in only_one)
    both = dv.open_questions(LAY, obs("A lone man was seen at the shutter.", "The guard heard a second person and a lookout outside."))
    people = next(a for a in both if a["key"] == "people")
    assert {o["id"] for o in people["options"]} == {"1", "2"}
    assert sum(1 for o in people["options"] if o["support"] == "best") == 1


def test_inside_knowledge_is_offered_when_there_are_signs_of_both():
    axes = dv.open_questions(LAY, obs("The shutter was pried with a crowbar.", "The alarm was disabled and he knew the layout."))
    assert any(a["key"] == "inside" for a in axes)
    assert not any(a["key"] == "inside" for a in dv.open_questions(LAY, obs("The shutter was pried with a crowbar.")))


def test_clock_and_unresolved_conflicts_become_questions_but_resolved_ones_do_not():
    ev = obs("x")
    ev["conflicts"] = [
        {"conflict_id": "C1", "claim_a": "CCTV overlay shows 02:20", "claim_b": "Alarm log shows 02:14", "nature_of_conflict": "timestamp offset", "review_status": "unresolved"},
        {"conflict_id": "C2", "claim_a": "The guard says the door was locked", "claim_b": "The manager says it was open", "review_status": "unresolved"},
        {"conflict_id": "C3", "claim_a": "a", "claim_b": "b", "review_status": "resolved"},
    ]
    keys = [a["key"] for a in dv.open_questions(LAY, ev)]
    assert "clock" in keys and "conflict:C2" in keys and "conflict:C3" not in keys and "conflict:C1" not in keys


# ---------------------------------------------------------------- branching

def test_each_scenario_flips_a_different_question_and_the_first_follows_the_evidence():
    axes = dv.open_questions(LAY, obs("A lone man.", "A second person and a lookout.", "Pried with a crowbar; alarm disabled, he knew the layout."))
    assert len(axes) >= 3
    plan = dv.assign_branches(axes)
    assert plan[0]["flips"] == []
    keys = [p["flips"][0]["key"] for p in plan[1:]]
    assert len(set(keys)) == 2
    assert all(f["option"]["support"] != "best" for p in plan for f in p["flips"])


def test_brief_names_every_question_and_every_scenario_and_asks_for_a_label():
    axes = dv.open_questions(LAY, obs("A lone man.", "A second person."))
    text = dv.brief_text(axes, dv.assign_branches(axes))
    assert "Scenario 1" in text and "Scenario 2" in text and "Scenario 3" in text and "differs_by" in text and "less_supported" in text
    assert "Which outside door" in text


def test_with_no_open_question_the_brief_still_demands_real_differences():
    text = dv.brief_text([], dv.assign_branches([]))
    assert "at least two real ways" in text


# ---------------------------------------------------------------- measuring difference

def test_the_same_story_twice_is_too_similar_and_a_different_entry_is_not():
    base = [S("a", "exterior", "approach"), S("a", "rear", "damage", effects=[{"target": "rear", "state": "forced"}]), S("a", "safe", "take_item", item="jewels"), S("a", "exterior", "flee")]
    other = [S("a", "front", "unlock", effects=[{"target": "front", "state": "unlocked"}]), S("a", "till", "take_item", item="cash"), S("a", "exterior", "flee")]
    s1, s2, s3 = scn(base), scn(base), scn(other)
    pairs = dv.pairwise([s1, s2, s3], LAY)
    same = next(p for p in pairs if (p["a"], p["b"]) == (0, 1))
    diff = next(p for p in pairs if (p["a"], p["b"]) == (0, 2))
    assert same["too_similar"] and same["distance"] == 0.0
    assert not diff["too_similar"] and diff["distance"] > dv.MIN_DISTANCE and "entry" in diff["differs_in"]


def test_one_thief_versus_two_is_a_real_difference():
    steps1 = [S("a", "exterior", "approach"), S("a", "rear", "damage", effects=[{"target": "rear", "state": "forced"}]), S("a", "safe", "take_item", item="jewels")]
    steps2 = steps1 + [S("b", "exterior", "wait"), S("b", "till", "take_item", item="cash")]
    d, ways = dv.distance(dv.signature(scn(steps1), LAY), dv.signature(scn(steps2, ACT), LAY))
    assert "number of people" in ways and d > dv.MIN_DISTANCE


def test_reordering_the_key_actions_counts_but_rewording_does_not():
    a = [S("a", "exterior", "approach"), S("a", "rear", "damage", effects=[{"target": "rear", "state": "forced"}]), S("a", "safe", "take_item", item="jewels"), S("a", "till", "take_item", item="cash")]
    b = [S("a", "exterior", "approach"), S("a", "rear", "damage", narrative="forces the lock", effects=[{"target": "rear", "state": "forced"}]),
         S("a", "safe", "take_item", item="jewels", narrative="grabs the jewels"), S("a", "till", "take_item", item="cash")]
    c = [S("a", "exterior", "approach"), S("a", "rear", "damage", effects=[{"target": "rear", "state": "forced"}]), S("a", "till", "take_item", item="cash"), S("a", "safe", "take_item", item="jewels")]
    assert dv.distance(dv.signature(scn(a), LAY), dv.signature(scn(b), LAY))[0] == 0.0
    assert dv.distance(dv.signature(scn(a), LAY), dv.signature(scn(c), LAY))[0] > 0.0


def test_repair_note_names_the_pair_and_the_ways_to_differ():
    note = dv.repair_note([{"a": 0, "b": 1, "distance": 0.04}], [])
    assert "scenarios 1 and 2" in note and "different entry" in note and "Do not just reword" in note
