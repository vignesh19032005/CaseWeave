"""When can each camera and witness see each person? The ranges must agree with the line-of-sight test the validator uses."""
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from pipeline import sandbox, sandbox_geometry as sg  # noqa: E402

RAW = {
    "rooms": [{"id": "shop", "label": "Shop floor", "width_m": 10, "length_m": 8}, {"id": "store", "label": "Stockroom", "width_m": 6, "length_m": 5, "attach": {"to": "shop", "wall": "north", "align_frac": 0.2}}],
    "entry_points": [{"id": "front", "label": "Front door", "room": "shop", "wall": "south", "position_frac": 0.5, "width_m": 1.4, "state": "intact"},
                     {"id": "rear", "label": "Rear shutter", "room": "store", "wall": "north", "position_frac": 0.5, "width_m": 2.0, "state": "forced"}],
    "connections": [{"id": "inner", "label": "Inner door", "room_a": "shop", "room_b": "store", "position_frac": 0.5, "width_m": 1.0, "state": "open"}],
    "fixtures": [{"id": "counter", "label": "Counter", "room": "shop", "position_frac": [0.5, 0.4], "footprint_m": [3, 0.8], "height_m": 1},
                 {"id": "shelf", "label": "Shelf", "room": "store", "position_frac": [0.5, 0.5], "footprint_m": [3, 0.5], "height_m": 1.9}],
    "key_locations": [{"id": "till", "label": "Till", "room": "shop", "position_frac": [0.5, 0.4]}],
}
RAW["observers"] = [
    {"id": "cam", "label": "Shop camera", "kind": "camera", "room": "shop", "position_frac": [0.05, 0.05], "facing_toward": "counter", "fov_deg": 100, "range_m": 14},
    {"id": "store_cam", "label": "Store camera", "kind": "camera", "room": "store", "position_frac": [0.1, 0.1], "facing_toward": "shelf", "fov_deg": 100, "range_m": 10},
    {"id": "wit", "label": "Night guard Ravi at the lane", "kind": "witness", "room": "outside", "near": "rear", "distance_m": 6, "lateral_m": 0, "fov_deg": 140, "range_m": 25},
]
LAY = sg.build_layout(RAW, set())
SC = sg.get_scene(LAY)


def S(actor, node, action, dt=10, **kw):
    return {"actor": actor, "node_id": node, "action": action, "dt_sec_estimate": dt, "narrative": "", **kw}


ACT = [{"id": "a", "label": "Thief", "role": "suspect"}, {"id": "g", "label": "Night guard Ravi", "role": "witness"}]
STEPS = [S("a", "exterior", "approach"), S("a", "rear", "damage", 20), S("a", "till", "take_item", 15, item="cash"), S("a", "exterior", "flee"), S("g", "wit", "look", 30)]


def plan():
    return sg.plan_scenario(STEPS, LAY, ACT)


def ranges_for(vis, observer, person):
    return next((v["ranges"] for v in vis if v["observer"] == observer and v["person"] == person), [])


def inside(ranges, t):
    return any(r[0] - 1e-6 <= t <= r[1] + 1e-6 for r in ranges)


def test_ranges_exist_are_sorted_non_overlapping_and_inside_the_scenario():
    p = plan()
    vis = sg.visibility_ranges(p, LAY)
    assert vis, "somebody should be seen by somebody"
    for v in vis:
        prev = -1.0
        for r in v["ranges"]:
            assert 0.0 <= r[0] < r[1] <= p["total_duration_s"] + 1e-6 and r[0] >= prev
            prev = r[1]
        assert v["seen_for_s"] == round(sum(r[1] - r[0] for r in v["ranges"]), 1) and v["kind"] in ("camera", "witness")


def test_every_sampled_moment_agrees_with_the_validators_own_line_of_sight_test():
    p = plan()
    vis = sg.visibility_ranges(p, LAY)
    mismatches = 0
    checked = 0
    for ob in LAY["observers"]:
        for a in p["actors"]:
            spot = sg._witness_spot_for({"id": a["id"], "label": a["label"]}, LAY)
            if spot is not None and spot["id"] == ob["id"]:
                continue   # nobody is counted as watching themselves
            t = a["segments"][0]["t0"]
            while t <= a["segments"][-1]["t1"]:
                pos = sg._actor_pos_at(a, t)
                ok, _ = SC.visible(ob, pos, pos[1])
                if ok != inside(ranges_for(vis, ob["id"], a["id"]), t):
                    # a sample on the very edge of a range may fall either side of it
                    near_edge = any(abs(t - e) <= sg.VISIBILITY_STEP_S + 1e-6 for r in ranges_for(vis, ob["id"], a["id"]) for e in r)
                    mismatches += 0 if near_edge else 1
                checked += 1
                t += 0.37
    assert checked > 100 and mismatches == 0


def test_a_camera_in_another_room_never_sees_someone_who_is_never_in_its_room_or_view():
    p = plan()
    vis = sg.visibility_ranges(p, LAY)
    shop_cam = sum(v["seen_for_s"] for v in vis if v["observer"] == "cam" and v["person"] == "a")
    assert shop_cam > 0                                                                    # the thief is seen at the till
    store_at_till = [r for r in ranges_for(vis, "store_cam", "a") if any(inside([r], g["t0"] + 1) for g in p["actors"][0]["segments"] if g["node_id"] == "till" and g["kind"] == "dwell")]
    assert store_at_till == []                                                             # a wall is between the store camera and the till


def test_nobody_is_counted_as_watching_themselves():
    vis = sg.visibility_ranges(plan(), LAY)
    assert not any(v["observer"] == "wit" and v["person"] == "g" for v in vis)


def test_nobody_is_counted_before_their_first_step_or_after_their_last():
    p = plan()
    vis = sg.visibility_ranges(p, LAY)
    for v in vis:
        a = next(x for x in p["actors"] if x["id"] == v["person"])
        assert all(r[0] >= a["segments"][0]["t0"] - 1e-6 and r[1] <= a["segments"][-1]["t1"] + 1e-6 for r in v["ranges"])


def test_a_claimed_sighting_falls_inside_the_computed_ranges():
    steps = [S("a", "exterior", "approach"), S("a", "till", "take_item", 15, item="cash", observed_by=["cam"]), S("a", "exterior", "flee")]
    p = sg.plan_scenario(steps, LAY, ACT[:1])
    claim = p["observation_claims"][0]
    val = sg.validate_plan(p, LAY)
    assert next(c for c in val["observation_checks"] if c["observer"] == "cam")["visible"] is True
    vis = sg.visibility_ranges(p, LAY)
    assert inside(ranges_for(vis, "cam", "a"), (claim["t0"] + claim["t1"]) / 2)


def test_no_observers_or_no_people_gives_nothing_and_never_fails():
    lay = sg.build_layout({k: v for k, v in RAW.items() if k != "observers"}, set())
    assert sg.visibility_ranges(sg.plan_scenario(STEPS[:4], lay, ACT[:1]), lay) == []
    assert sg.visibility_ranges({"actors": [], "total_duration_s": 0}, LAY) == []


def test_it_is_fast_enough_to_run_on_every_scenario():
    p = plan()
    t0 = time.time()
    sg.visibility_ranges(p, LAY)
    assert time.time() - t0 < 4.0


def test_the_ranges_ride_along_with_every_built_scenario():
    ev = {"evidence_items": [], "observations": [{"observation_id": "OBS-1", "description": "x", "extracted_time": "01:00", "classification": "fact", "source_evidence_id": "EV-1"}],
          "entities": [], "conflicts": [], "relationships": [], "timeline": []}
    raw = {"title": "T", "hypothesis_summary": "s", "plausibility_estimate": 60, "actors": ACT, "steps": STEPS, "supporting_facts": [], "contradicted_points": []}
    scn = sandbox._build_scenario(raw, LAY, ev, sandbox._scenario_context(ev))
    assert scn["visibility"] and all({"observer", "person", "ranges", "seen_for_s"} <= set(v) for v in scn["visibility"])
