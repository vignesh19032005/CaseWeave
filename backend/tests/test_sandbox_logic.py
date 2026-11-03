"""Situational logic: hand-overs, items, people who lie down, closed doors, people in the same spot,
and people with no named position. Only the logically impossible is rejected; what the evidence may
simply not mention is a caution."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from pipeline import sandbox_geometry as sg  # noqa: E402

RAW = {
    "rooms": [{"id": "shop", "width_m": 8, "length_m": 6}, {"id": "store", "width_m": 6, "length_m": 5, "attach": {"to": "shop", "wall": "north", "align_frac": 0.2}}],
    "entry_points": [{"id": "front", "room": "shop", "wall": "south", "position_frac": 0.5, "width_m": 1.4, "state": "intact"},
                     {"id": "rear", "room": "store", "wall": "north", "position_frac": 0.5, "width_m": 1.6, "state": "intact"}],
    "connections": [{"id": "inner", "room_a": "shop", "room_b": "store", "position_frac": 0.5, "width_m": 1.0, "state": "open"}],
    "fixtures": [{"id": "till", "room": "shop", "position_frac": [0.5, 0.4], "footprint_m": [2, 0.7], "height_m": 1.0},
                 {"id": "safe", "room": "store", "position_frac": [0.5, 0.7], "footprint_m": [0.8, 0.6], "height_m": 1.0}],
}
LAY = sg.build_layout(RAW, set())
ACTORS = [{"id": "a", "label": "Thief", "role": "suspect"}, {"id": "b", "label": "Other", "role": "suspect"}, {"id": "v", "label": "Victim", "role": "victim"}]


def S(actor, node, action, dt=10, **kw):
    return {"actor": actor, "node_id": node, "action": action, "dt_sec_estimate": dt, "narrative": "", **kw}


def check(steps, actors=ACTORS):
    plan = sg.plan_scenario(steps, LAY, actors)
    val = sg.validate_plan(plan, LAY)
    return val, plan


def codes(v):
    return {x["code"] for x in v["violations"]}


def says(v, text):
    return any(text in w for w in v["warnings"])


def test_handover_with_nobody_receiving_is_a_caution():
    v, _ = check([S("a", "till", "hand_over"), S("a", "safe", "search")])
    assert "handover_apart" not in codes(v) and says(v, "nobody is shown receiving it")


def test_handover_to_someone_far_away_is_rejected():
    v, _ = check([S("a", "till", "hand_over"), S("b", "safe", "receive")])
    assert "handover_apart" in codes(v) and not v["is_physically_possible"]


def test_handover_to_someone_beside_them_at_the_same_time_is_accepted():
    v, _ = check([S("a", "till", "hand_over", 15), S("b", "till", "receive", 15)])
    assert "handover_apart" not in codes(v)


def test_receiving_with_nobody_handing_over_is_a_caution():
    v, _ = check([S("a", "till", "search"), S("b", "safe", "receive")])
    assert says(v, "nobody is shown handing it over")


def test_putting_down_something_never_picked_up_is_only_a_caution():
    v, _ = check([S("a", "till", "drop_item", item="knife"), S("a", "safe", "search")])
    assert says(v, "puts down 'knife'") and v["is_physically_possible"]


def test_picking_up_then_putting_down_raises_no_item_caution():
    v, _ = check([S("a", "till", "take_item", item="cash"), S("a", "safe", "drop_item", item="cash")])
    assert not says(v, "no step shows them picking it up")


def test_carrying_several_things_is_fine():
    v, _ = check([S("a", "till", "take_item", item="cash"), S("a", "safe", "take_item", item="jewels"), S("a", "till", "drop_item", item="cash")])
    assert not any("picking it up" in w for w in v["warnings"]) and v["is_physically_possible"]


def test_someone_who_lies_down_and_walks_on_gets_a_caution_not_a_rejection():
    v, _ = check([S("v", "till", "lie_down"), S("v", "safe", "move")])
    assert says(v, "with no step showing them getting up") and v["is_physically_possible"]


def test_getting_up_clears_it():
    v, _ = check([S("v", "till", "lie_down"), S("v", "till", "stand"), S("v", "safe", "move")])
    assert not says(v, "getting up")


def test_forcing_something_with_no_tool_mentioned_is_a_caution():
    v, _ = check([S("a", "exterior", "approach"), S("a", "rear", "damage", effects=[{"target": "rear", "state": "forced"}]), S("a", "safe", "search")])
    assert says(v, "no tool is mentioned")
    v2, _ = check([S("a", "exterior", "approach"), S("a", "rear", "damage", item="crowbar", effects=[{"target": "rear", "state": "forced"}]), S("a", "safe", "search")])
    assert not says(v2, "no tool is mentioned")


def test_going_through_a_closed_unforced_outside_door_is_a_caution_but_forcing_it_first_clears_it():
    v, _ = check([S("a", "exterior", "approach"), S("a", "safe", "search"), S("a", "exterior", "flee")])
    assert says(v, "recorded as closed and not forced")
    v2, _ = check([S("a", "exterior", "approach"), S("a", "rear", "damage", effects=[{"target": "rear", "state": "forced"}]), S("a", "safe", "search")])
    assert not says(v2, "recorded as closed and not forced")


def test_walking_up_to_a_door_is_not_passing_through_it():
    v, _ = check([S("a", "exterior", "approach"), S("a", "rear", "open", effects=[{"target": "rear", "state": "opened"}]), S("a", "safe", "search")])
    assert not says(v, "recorded as closed and not forced")


def test_two_people_in_the_same_spot_for_a_while_get_a_caution():
    v, _ = check([S("a", "till", "search", 30), S("b", "till", "search", 30)])
    assert says(v, "exactly the same spot")


def test_two_people_at_different_places_do_not():
    v, _ = check([S("a", "till", "search", 30), S("b", "safe", "search", 30)])
    assert not says(v, "exactly the same spot")


def test_a_person_with_no_named_place_outside_is_told_where_they_are_shown():
    v, plan = check([S("a", "exterior", "approach"), S("a", "till", "search")])
    seg = plan["actors"][0]["segments"][0]
    assert seg["routing_notes"] and "no place outside is named" in seg["routing_notes"][0]
    assert any("no place outside is named" in n for st in plan["actors"][0]["steps"] for n in st["route_notes"])


def test_the_checks_are_listed_for_the_reader():
    v, _ = check([S("a", "till", "search"), S("a", "safe", "search")])
    assert any("hand-over" in c for c in v["checks_run"]) and any("lies down" in c for c in v["checks_run"])


# ---------------------------------------------------------------- people are brought together in time

def _arrive_of(plan, aid, k):
    return next(st["arrive_s"] for a in plan["actors"] if a["id"] == aid for st in a["steps"] if st["k"] == k)


def test_a_hand_over_and_its_receive_are_brought_into_the_same_moment():
    actors = [{"id": "a", "label": "Thief", "role": "suspect"}, {"id": "b", "label": "Other", "role": "suspect", "start_offset_s": 90}]
    steps = [S("a", "till", "take_item", item="cash"), S("a", "till", "hand_over", item="cash"), S("b", "till", "receive")]
    plan = sg.plan_scenario(steps, LAY, actors)
    val = sg.validate_plan(plan, LAY)
    assert abs(_arrive_of(plan, "a", 1) - _arrive_of(plan, "b", 0)) <= sg.SYNC_TOL_S
    assert "handover_apart" not in {v["code"] for v in val["violations"]}
    assert plan["sync"]["waits"] and plan["sync"]["waits"][0]["actor"] == "a"           # the one who was early waited
    giver = next(a for a in plan["actors"] if a["id"] == "a")
    assert any(g["action"] == "wait" and g["phase"] == "waits" for g in giver["segments"])
    assert all(giver["segments"][i]["t1"] <= giver["segments"][i + 1]["t0"] + 1e-6 for i in range(len(giver["segments"]) - 1))   # still one unbroken timeline


def test_steps_the_scenario_links_with_sync_with_happen_together():
    actors = [{"id": "a", "label": "Thief", "role": "suspect"}, {"id": "w", "label": "Guard", "role": "witness", "start_offset_s": 0}]
    steps = [S("a", "exterior", "approach"), S("a", "rear", "damage", 30), S("a", "till", "search", 20),
             S("w", "exterior", "look", 10), S("w", "front", "look", 10, sync_with={"actor": "a", "step": 3})]
    plan = sg.plan_scenario(steps, LAY, actors)
    assert abs(_arrive_of(plan, "w", 1) - _arrive_of(plan, "a", 2)) <= sg.SYNC_TOL_S
    st = next(s for a in plan["actors"] if a["id"] == "w" for s in a["steps"] if s["k"] == 1)
    assert st["sync_with"] == {"actor": "a", "step": 3}


def test_a_huge_gap_is_not_papered_over_it_is_reported():
    actors = [{"id": "a", "label": "Thief", "role": "suspect"}, {"id": "b", "label": "Other", "role": "suspect", "start_offset_s": 3900}]
    steps = [S("a", "till", "take_item", item="cash"), S("a", "till", "hand_over", item="cash"), S("b", "till", "receive")]
    plan = sg.plan_scenario(steps, LAY, actors)
    val = sg.validate_plan(plan, LAY)
    assert plan["sync"]["waits"] == [] and plan["sync"]["not_brought_together"]
    assert "handover_apart" in {v["code"] for v in val["violations"]} and any("too far apart" in w for w in val["warnings"])


def test_scenarios_with_nothing_to_synchronise_are_planned_exactly_as_before():
    plan = sg.plan_scenario([S("a", "exterior", "approach"), S("a", "till", "search")], LAY, ACTORS[:1])
    assert plan["sync"] == {"waits": [], "not_brought_together": []}
    assert not any(g["action"] == "wait" for a in plan["actors"] for g in a["segments"])


def test_a_bad_sync_reference_is_ignored_safely():
    steps = [S("a", "exterior", "approach"), S("a", "till", "search", sync_with={"actor": "nobody", "step": 7}), S("a", "safe", "search", sync_with="garbage")]
    plan = sg.plan_scenario(steps, LAY, ACTORS[:1])
    assert plan["ok"] and plan["sync"]["waits"] == []
