"""Property and unit tests for the scene geometry engine (schema 3).

Core promise: no plan the engine produces may pass through a wall or
furniture and still be reported as physically possible. The validator that
makes that call is independent of the router and is itself tested against
deliberately bad paths. Layouts are built from random, often nonsensical model
output (many rooms, floors, doors, people) to prove nothing crashes and
nothing slips through.
"""
import json
import math
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import sandbox_geometry as sg  # noqa: E402


# ---------------------------------------------------------------- random inputs

def random_raw(rng: random.Random) -> dict:
    n = rng.randint(1, 6)
    rooms = []
    for i in range(n):
        r = {"id": f"r{i}", "width_m": rng.uniform(1, 40), "length_m": rng.uniform(1, 30), "height_m": rng.uniform(2, 7)}
        if i > 0 and rng.random() < 0.9:
            r["attach"] = {"to": f"r{rng.randrange(i)}", "wall": rng.choice(["north", "south", "east", "west", "above", "below", "up"]), "align_frac": rng.random()}
        if rng.random() < 0.15:
            r["observed"] = False
        rooms.append(r)
    conns = [{"id": f"c{k}", "room_a": f"r{rng.randrange(n)}", "room_b": f"r{rng.randrange(n)}", "position_frac": rng.random(),
              "width_m": rng.uniform(0.3, 3), "state": rng.choice(["open", "forced", "intact", "locked", "unknown", "??"]),
              "kind": rng.choice(["door", "door", "stairs"])} for k in range(rng.randint(0, 6))]
    entries = [{"id": f"e{k}", "room": f"r{rng.randrange(n)}", "wall": rng.choice(["north", "south", "east", "west", "up"]),
                "position_frac": rng.random(), "width_m": rng.uniform(0.3, 4), "state": rng.choice(["open", "forced", "intact", "locked", "unknown"])}
               for k in range(rng.randint(0, 4))]
    fixtures = [{"id": f"f{k}", "room": f"r{rng.randrange(n)}", "position_frac": [rng.random(), rng.random()],
                 "footprint_m": [rng.uniform(0.2, 6), rng.uniform(0.2, 6)], "height_m": rng.uniform(0.2, 3)} for k in range(rng.randint(0, 10))]
    keys = [{"id": f"k{k}", "room": rng.choice([f"r{rng.randrange(n)}", "outside"]), "position_frac": [rng.random(), rng.random()],
             "near": f"e{rng.randrange(3)}", "distance_m": rng.uniform(0, 10)} for k in range(rng.randint(0, 5))]
    outdoor = [{"id": f"o{k}", "near": f"e{rng.randrange(3)}", "distance_m": rng.uniform(0, 10), "lateral_m": rng.uniform(-8, 8),
                "footprint_m": [rng.uniform(0.5, 4), rng.uniform(0.5, 4)], "kind": "vehicle"} for k in range(rng.randint(0, 3))]
    obs = [{"id": f"cam{k}", "kind": rng.choice(["camera", "witness"]), "room": rng.choice([f"r{rng.randrange(n)}", "outside"]),
            "position_frac": [rng.random(), rng.random()], "near": f"e{rng.randrange(3)}", "distance_m": rng.uniform(1, 8)} for k in range(rng.randint(0, 3))]
    return {"rooms": rooms, "connections": conns, "entry_points": entries, "fixtures": fixtures, "key_locations": keys,
            "outdoor_objects": outdoor, "observers": obs}


def node_ids(layout: dict) -> list:
    return [n["id"] for g in ("rooms", "openings", "fixtures", "key_locations", "outdoor_objects", "observers") for n in layout.get(g, [])]


def random_steps(rng: random.Random, layout: dict):
    ids = node_ids(layout) + ["exterior", "unknown_place"]
    n_actors = rng.randint(1, 4)
    actors = [{"id": f"a{i}", "label": f"Person {i}", "start_offset_s": rng.choice([0, 0, 30, "20 seconds"])} for i in range(n_actors)]
    steps = []
    obs = [o["id"] for o in layout.get("observers", [])]
    for ai in range(n_actors):
        steps.append({"actor": f"a{ai}", "node_id": "exterior", "action": "approach", "dt_sec_estimate": rng.choice([5, 30])})
        for _ in range(rng.randint(1, 8)):
            st = {"actor": f"a{ai}", "node_id": rng.choice(ids), "action": rng.choice(list(sg.ACTIONS) + ["dance"]),
                  "dt_sec_estimate": rng.choice([3, 10, 45, 200, "2 minutes", None, "soon"])}
            if rng.random() < 0.2 and obs:
                st["observed_by"] = [rng.choice(obs)]
            if rng.random() < 0.2:
                st["effects"] = [{"target": rng.choice(ids), "state": rng.choice(["forced", "opened", "bogus"])}]
            steps.append(st)
        if rng.random() < 0.7:
            steps.append({"actor": f"a{ai}", "node_id": "exterior", "action": "flee", "dt_sec_estimate": 20})
    return steps, actors


def blocked(val):
    return [v for v in val["violations"] if v["code"] in ("path_blocked", "stop_blocked", "discontinuous")]


DISCLOSED = {"unreachable", "no_route", "door_too_narrow", "too_few_steps"}


# ---------------------------------------------------------------- coercion

def test_coercion_never_raises():
    assert sg.to_float("about 12 metres") == 12.0
    assert sg.to_float("n/a", 5.0) == 5.0
    assert sg.to_float(0) == 0.0
    assert sg.to_float(True, 9.0) == 9.0
    assert sg.to_float(float("nan"), 2.0) == 2.0
    assert sg.to_seconds("2 minutes", 30) == 120.0
    assert sg.to_seconds({"x": 1}, 30) == 30.0
    assert sg.normalize_id("Back Room!") == "back_room"


@pytest.mark.parametrize("raw", [None, [], "text", 5, {}, {"rooms": "x"}, {"rooms": [None, 3, {"id": 7}]},
                                 {"width_m": "huge", "entry_points": "door", "fixtures": [1, None, "x"], "key_locations": [{"id": ["a"]}]}])
def test_build_layout_survives_garbage(raw):
    lay = sg.build_layout(raw, {"OBS-1"})
    assert lay["schema_version"] == sg.SCHEMA_VERSION and lay["rooms"]
    assert any(o["kind"] == "external" for o in lay["openings"]), "a way in must always exist (flagged as assumed)"
    assert lay["defaults_used"]


def test_default_door_and_size_are_flagged_not_silent():
    lay = sg.build_layout({}, set())
    ext = [o for o in lay["openings"] if o["kind"] == "external"][0]
    assert ext["basis"] == "assumed" and any("entrance" in d for d in lay["defaults_used"]) and lay["dimensions_basis"] == "assumed"


def test_zero_position_is_respected():
    lay = sg.build_layout({"rooms": [{"id": "a", "width_m": 10, "length_m": 10}], "fixtures": [{"id": "f", "room": "a", "position_frac": [0.0, 0.0], "footprint_m": [1, 1]}]}, set())
    fx = lay["fixtures"][0]
    assert fx["pos"][0] < -3.5 and fx["pos"][2] < -3.5


def test_reserved_and_duplicate_ids_rejected_across_kinds():
    lay = sg.build_layout({"rooms": [{"id": "a", "width_m": 8, "length_m": 8}, {"id": "exterior", "width_m": 5, "length_m": 5, "attach": {"to": "a", "wall": "east"}}],
                           "fixtures": [{"id": "a"}, {"id": "desk", "room": "a"}, {"id": "DESK", "room": "a"}]}, set())
    assert [r["id"] for r in lay["rooms"]][0] == "a" and "exterior" not in [r["id"] for r in lay["rooms"]]
    assert [f["id"] for f in lay["fixtures"]] == ["desk"]


def test_citations_only_kept_if_known():
    lay = sg.build_layout({"rooms": [{"id": "a", "width_m": 8, "length_m": 8, "evidence_refs": ["OBS-FAKE"], "basis": "stated"}],
                           "fixtures": [{"id": "f", "room": "a", "evidence_refs": ["OBS-1", "OBS-FAKE"], "basis": "stated"}]}, {"OBS-1"})
    assert lay["fixtures"][0]["evidence_refs"] == ["OBS-1"] and lay["fixtures"][0]["basis"] == "stated"
    assert lay["rooms"][0]["basis"] == "assumed", "cannot claim 'stated' without a real citation"


# ---------------------------------------------------------------- rooms and floors

def test_rooms_attach_share_walls_and_never_overlap():
    lay = sg.build_layout({"rooms": [
        {"id": "a", "width_m": 10, "length_m": 8},
        {"id": "b", "width_m": 6, "length_m": 5, "attach": {"to": "a", "wall": "east", "align_frac": 0}},
        {"id": "c", "width_m": 6, "length_m": 5, "attach": {"to": "a", "wall": "east", "align_frac": 0}},  # same slot: must move
    ]}, set())
    rs = {r["id"]: r["rect"] for r in lay["rooms"]}
    assert abs(rs["b"][0] - rs["a"][1]) < 1e-6, "rooms share the wall line"
    assert sg._overlap_area(tuple(rs["b"]), tuple(rs["c"])) < 0.04
    assert any("side" in w for w in lay["warnings"]), "moving a room must be disclosed"


def test_upper_floor_and_basement_heights():
    lay = sg.build_layout({"rooms": [{"id": "g", "width_m": 8, "length_m": 8, "height_m": 3},
                                     {"id": "up", "width_m": 8, "length_m": 8, "height_m": 3, "attach": {"to": "g", "wall": "above"}},
                                     {"id": "bs", "width_m": 8, "length_m": 8, "height_m": 3, "attach": {"to": "g", "wall": "below"}}]}, set())
    ys = {r["id"]: r["floor_y"] for r in lay["rooms"]}
    assert ys["g"] == 0 and ys["up"] > 3 and ys["bs"] < -3


def test_unplaceable_room_is_dropped_and_reported():
    lay = sg.build_layout({"rooms": [{"id": "a", "width_m": 8, "length_m": 8}, {"id": "x", "width_m": 4, "length_m": 4, "attach": {"to": "ghost", "wall": "east"}}]}, set())
    assert [r["id"] for r in lay["rooms"]] == ["a"] and any("ghost" in w for w in lay["warnings"])


def test_door_only_between_rooms_that_share_a_wall():
    raw = {"rooms": [{"id": "a", "width_m": 8, "length_m": 8}, {"id": "b", "width_m": 5, "length_m": 5, "attach": {"to": "a", "wall": "east"}},
                     {"id": "far", "width_m": 5, "length_m": 5, "attach": {"to": "b", "wall": "east"}}],
           "connections": [{"id": "ab", "room_a": "a", "room_b": "b", "width_m": 1}, {"id": "af", "room_a": "a", "room_b": "far", "width_m": 1}]}
    lay = sg.build_layout(raw, set())
    ids = [o["id"] for o in lay["openings"]]
    assert "ab" in ids and "af" not in ids and any("do not share a wall" in w for w in lay["warnings"])


def test_outside_door_cannot_open_into_another_room():
    raw = {"rooms": [{"id": "a", "width_m": 8, "length_m": 8}, {"id": "b", "width_m": 8, "length_m": 8, "attach": {"to": "a", "wall": "east", "align_frac": 0.5}}],
           "entry_points": [{"id": "x", "room": "a", "wall": "east", "position_frac": 0.5, "width_m": 1}]}
    lay = sg.build_layout(raw, set())
    assert "x" not in [o["id"] for o in lay["openings"]], "that wall is entirely shared with room b"
    assert any(o["id"] == "main_entry" for o in lay["openings"]), "a fallback way in is created and flagged"


# ---------------------------------------------------------------- layout invariants (random)

@pytest.mark.parametrize("seed", range(80))
def test_layout_invariants(seed):
    rng = random.Random(seed)
    lay = sg.build_layout(random_raw(rng), set())
    t2 = lay["wall_thickness_m"] / 2
    rooms = {r["id"]: r for r in lay["rooms"]}
    for a in lay["rooms"]:
        for b in lay["rooms"]:
            if a["id"] < b["id"] and a["level"] == b["level"]:
                assert sg._overlap_area(tuple(a["rect"]), tuple(b["rect"])) < 0.05, "rooms overlap"
    soft = any("could not be separated" in w or "could not be moved clear" in w for w in lay["warnings"])
    for fx in lay["fixtures"]:
        x0, x1, z0, z1 = sg._fixture_rect(fx)
        r = rooms[fx["room"]]["rect"]
        assert x0 >= r[0] + t2 - 1e-3 and x1 <= r[1] - t2 + 1e-3 and z0 >= r[2] + t2 - 1e-3 and z1 <= r[3] - t2 + 1e-3, "furniture pokes through a wall"
    if not soft:
        by_room = {}
        for fx in lay["fixtures"]:
            by_room.setdefault(fx["room"], []).append(fx)
        for rid, group in by_room.items():
            for i, a in enumerate(group):
                for b in group[:i]:
                    assert sg._overlap_push(sg._fixture_rect(a), sg._fixture_rect(b)) is None, "furniture overlaps"
                for op in lay["openings"]:
                    if op["kind"] != "stairs" and rid in (op["room_a"], op["room_b"]):
                        assert sg._overlap_push(sg._fixture_rect(a), sg._zone_in_room(op, rid)) is None, "furniture blocks a door"
    for op in lay["openings"]:
        if op["kind"] == "stairs":
            assert abs(rooms[op["room_a"]]["level"] - rooms[op["room_b"]]["level"]) == 1
            continue
        ra = rooms[op["room_a"]]
        orient, line, e0, e1 = sg._edge_of(ra, op["wall"])
        assert orient == op["orient"] and abs(line - op["line"]) < 1e-3
        assert e0 - 1e-3 <= op["gap_center_m"] - op["width_m"] / 2 and op["gap_center_m"] + op["width_m"] / 2 <= e1 + 1e-3, "door does not fit its wall"
        if op["kind"] == "external":
            assert ra["level"] == 0
    seen = {}
    for op in lay["openings"]:
        if op["kind"] != "stairs":
            seen.setdefault((op["orient"], round(op["line"], 3), op["level"]), []).append(op)
    for ops in seen.values():
        ops.sort(key=lambda o: o["gap_center_m"])
        for a, b in zip(ops, ops[1:]):
            assert b["gap_center_m"] - b["width_m"] / 2 >= a["gap_center_m"] + a["width_m"] / 2 - 1e-3, "doors overlap"
    for n in sg.all_nodes(lay):
        assert n["basis"] in ("stated", "inferred", "assumed")
        assert "reachable" in n and "stand_pos" in n


# ---------------------------------------------------------------- the main promise

@pytest.mark.parametrize("seed", range(120))
def test_no_undisclosed_blocked_paths_any_rooms_any_people(seed):
    rng = random.Random(1000 + seed)
    lay = sg.build_layout(random_raw(rng), set())
    steps, actors = random_steps(rng, lay)
    plan = sg.plan_scenario(steps, lay, actors)
    val = sg.validate_plan(plan, lay)
    bad = blocked(val)
    disclosed = [v for v in val["violations"] if v["code"] in DISCLOSED]
    assert not (bad and not disclosed), f"seed {seed}: undisclosed blocked path: {bad[:2]}"
    if bad or disclosed:
        assert not val["is_physically_possible"]


@pytest.mark.parametrize("seed", range(40))
def test_planning_is_deterministic(seed):
    rng = random.Random(7000 + seed)
    lay = sg.build_layout(random_raw(rng), set())
    steps, actors = random_steps(rng, lay)
    a = json.dumps(sg.plan_scenario(steps, lay, actors), sort_keys=True, default=str)
    b = json.dumps(sg.plan_scenario(steps, lay, actors), sort_keys=True, default=str)
    assert a == b


@pytest.mark.parametrize("seed", range(60))
def test_timelines_are_consistent_per_person(seed):
    rng = random.Random(5000 + seed)
    lay = sg.build_layout(random_raw(rng), set())
    steps, actors = random_steps(rng, lay)
    plan = sg.plan_scenario(steps, lay, actors)
    for actor in plan["actors"]:
        t = actor["segments"][0]["t0"]
        assert abs(t - actor["start_offset_s"]) < 1e-2
        for s in actor["segments"]:
            assert abs(s["t0"] - t) < 1e-2, "gap or overlap in a person's timeline"
            assert s["t1"] >= s["t0"]
            t = s["t1"]
            if s["kind"] == "transit":
                assert s["action"] in ("move", "flee"), "actions must not happen while walking"
        arrive = [st["arrive_s"] for st in actor["steps"]]
        assert arrive == sorted(arrive)


# ---------------------------------------------------------------- validator is not fooled

def shop():
    return sg.build_layout({
        "rooms": [{"id": "shop", "width_m": 10, "length_m": 8}, {"id": "store", "width_m": 6, "length_m": 5, "attach": {"to": "shop", "wall": "north", "align_frac": 0.2}}],
        "entry_points": [{"id": "front", "room": "shop", "wall": "south", "position_frac": 0.5, "width_m": 1.4, "state": "intact"}],
        "connections": [{"id": "door", "room_a": "shop", "room_b": "store", "position_frac": 0.5, "width_m": 1.0, "state": "open"}],
        "fixtures": [{"id": "counter", "room": "shop", "position_frac": [0.5, 0.5], "footprint_m": [3, 0.8], "height_m": 1.0},
                     {"id": "shelf", "room": "store", "position_frac": [0.5, 0.5], "footprint_m": [3, 0.5], "height_m": 1.9}],
        "key_locations": [{"id": "till", "room": "shop", "position_frac": [0.5, 0.5]}, {"id": "stock", "room": "store", "position_frac": [0.5, 0.9]}],
    }, set())


def mk_plan(segments):
    return {"ok": True, "violations": [], "actors": [{"id": "a", "label": "A", "segments": segments, "end_s": segments[-1]["t1"], "steps": []}]}


def dwell(pos, t0=0, t1=1, step=0):
    return {"kind": "dwell", "t0": t0, "t1": t1, "step": step, "pos": pos, "action": "wait"}


def transit(pts, t0=1, t1=9, step=1, kinds=None):
    return {"kind": "transit", "t0": t0, "t1": t1, "step": step, "route": pts, "leg_kinds": kinds or ["walk"] * (len(pts) - 1),
            "leg_openings": [None] * (len(pts) - 1), "action": "move", "v_max": 1.4}


def test_validator_rejects_path_through_outer_wall():
    lay = shop()
    plan = mk_plan([dwell([3.0, 0.0, -6.0]), transit([[3.0, 0.0, -6.0], [3.0, 0.0, -2.0]])])
    assert any(v["code"] == "path_blocked" for v in sg.validate_plan(plan, lay)["violations"])


def test_validator_rejects_path_through_inner_wall():
    lay = shop()
    wall_z = lay["rooms"][0]["rect"][3]
    a, b = [-4.0, 0.0, wall_z - 1.0], [-4.0, 0.0, wall_z + 1.0]
    plan = mk_plan([dwell(a), transit([a, b])])
    assert any(v["code"] == "path_blocked" for v in sg.validate_plan(plan, lay)["violations"])


def test_validator_rejects_path_through_furniture_and_stop_inside_it():
    lay = shop()
    c = lay["fixtures"][0]["pos"]
    a, b = [c[0] - 3, 0.0, c[2]], [c[0] + 3, 0.0, c[2]]
    assert any(v["code"] == "path_blocked" for v in sg.validate_plan(mk_plan([dwell(a), transit([a, b])]), lay)["violations"])
    assert any(v["code"] == "stop_blocked" for v in sg.validate_plan(mk_plan([dwell(list(c))]), lay)["violations"])


def test_validator_accepts_proper_door_crossing_and_rejects_crossing_beside_it():
    lay = shop()
    d = [o for o in lay["openings"] if o["id"] == "front"][0]
    ok = mk_plan([dwell(d["outside_pos"]), transit([d["outside_pos"], d["gap_pos"], d["pos_a"]], kinds=["door", "door"])])
    assert sg.validate_plan(ok, lay)["violations"] == []
    off = d["gap_center_m"] + 3.0
    a, b = [off, 0.0, d["outside_pos"][2]], [off, 0.0, d["pos_a"][2]]
    assert any(v["code"] == "path_blocked" for v in sg.validate_plan(mk_plan([dwell(a), transit([a, b])]), lay)["violations"])


def test_validator_rejects_floor_change_off_stairs():
    lay = sg.build_layout({"rooms": [{"id": "g", "width_m": 8, "length_m": 8}, {"id": "u", "width_m": 8, "length_m": 8, "attach": {"to": "g", "wall": "above"}}]}, set())
    up = [r for r in lay["rooms"] if r["id"] == "u"][0]
    a, b = [0.0, 0.0, 0.0], [0.0, up["floor_y"], 0.0]
    assert any(v["code"] == "path_blocked" for v in sg.validate_plan(mk_plan([dwell(a), transit([a, b])]), lay)["violations"])


# ---------------------------------------------------------------- planning behaviours

def test_walk_in_search_through_inner_door_and_leave():
    lay = shop()
    steps = [{"node_id": "exterior", "action": "approach", "dt_sec_estimate": 5}, {"node_id": "stock", "action": "search", "dt_sec_estimate": 40},
             {"node_id": "till", "action": "take_item", "dt_sec_estimate": 30}, {"node_id": "exterior", "action": "flee", "dt_sec_estimate": 10}]
    plan = sg.plan_scenario(steps, lay)
    val = sg.validate_plan(plan, lay)
    assert val["is_physically_possible"], val["violations"]
    segs = plan["actors"][0]["segments"]
    till = [s for s in segs if s["kind"] == "dwell" and s["node_id"] == "till"][0]
    kp = lay["key_locations"][0]["pos"]
    assert till["face_pos"] == kp and (till["pos"][0], till["pos"][2]) != (kp[0], kp[2]), "stand beside, face the spot"
    assert any(s["auto_routed"] for s in segs if s["kind"] == "transit")
    assert plan["doors_used"], "doors used must be reported"


def test_people_do_not_share_a_timeline_and_offsets_apply():
    lay = shop()
    steps = [{"actor": "a", "node_id": "exterior", "dt_sec_estimate": 5}, {"actor": "a", "node_id": "till", "dt_sec_estimate": 20},
             {"actor": "b", "node_id": "exterior", "dt_sec_estimate": 5}, {"actor": "b", "node_id": "stock", "dt_sec_estimate": 20}]
    plan = sg.plan_scenario(steps, lay, [{"id": "a", "label": "A"}, {"id": "b", "label": "B", "start_offset_s": 40}])
    assert [a["id"] for a in plan["actors"]] == ["a", "b"]
    assert plan["actors"][1]["segments"][0]["t0"] == 40.0
    assert sg.validate_plan(plan, lay)["is_physically_possible"]
    assert len({a["color"] for a in plan["actors"]}) == 2


def test_unknown_location_and_unknown_person_are_dropped_and_reported():
    lay = shop()
    plan = sg.plan_scenario([{"node_id": "exterior"}, {"node_id": "secret room"}, {"actor": "zed", "node_id": "till"}, {"node_id": "till"}], lay)
    reasons = [d["reason"] for d in plan["dropped_steps"]]
    assert any("not part of the scene" in r for r in reasons) and any("not listed" in r for r in reasons)


def test_walking_time_comes_from_distance_and_follows_an_acceleration_profile():
    lay = shop()
    plan = sg.plan_scenario([{"node_id": "exterior", "dt_sec_estimate": 5}, {"node_id": "stock", "action": "search", "dt_sec_estimate": 1}], lay)
    tr = [s for s in plan["actors"][0]["segments"] if s["kind"] == "transit"][0]
    mean = tr["length_m"] / (tr["t1"] - tr["t0"])
    assert 0.9 <= mean <= 1.5 and tr["accel"] > 0 and tr["v_max"] > 0
    assert tr["t1"] - tr["t0"] > tr["length_m"] / tr["v_max"], "must be slower than constant top speed (accelerating and braking)"
    assert plan["time_adjustments"], "a too-short search must be disclosed as adjusted"


def test_transit_time_helpers_agree():
    for L in (0.5, 2.0, 10.0, 50.0):
        T = sg.transit_seconds(L, 1.4, 1.2)
        assert abs(sg._time_at_distance(L, L, 1.4, 1.2) - T) < 1e-6
        prev = 0.0
        for k in range(1, 11):
            t = sg._time_at_distance(L * k / 10, L, 1.4, 1.2)
            assert t >= prev
            prev = t


def test_running_is_faster_than_walking():
    lay = shop()
    walk = sg.plan_scenario([{"node_id": "exterior"}, {"node_id": "stock", "action": "move"}], lay)["actors"][0]["segments"]
    run = sg.plan_scenario([{"node_id": "exterior"}, {"node_id": "stock", "action": "flee"}], lay)["actors"][0]["segments"]
    tw = [s for s in walk if s["kind"] == "transit"][0]
    tr = [s for s in run if s["kind"] == "transit"][0]
    assert tr["t1"] - tr["t0"] < tw["t1"] - tw["t0"]


def test_unreachable_place_is_a_violation():
    lay = sg.build_layout({"rooms": [{"id": "a", "width_m": 4.4, "length_m": 6}],
                           "entry_points": [{"id": "d", "room": "a", "wall": "south", "position_frac": 0.5, "width_m": 1.2}],
                           "fixtures": [{"id": "wall_of_shelves", "room": "a", "position_frac": [0.5, 0.45], "footprint_m": [4.0, 0.8]}],
                           "key_locations": [{"id": "behind", "room": "a", "position_frac": [0.5, 0.97]}]}, set())
    plan = sg.plan_scenario([{"node_id": "exterior"}, {"node_id": "behind", "dt_sec_estimate": 120}], lay)
    val = sg.validate_plan(plan, lay)
    assert not val["is_physically_possible"] and any(v["code"] in ("unreachable", "no_route") for v in val["violations"])


def test_forced_door_preferred_and_intact_door_avoided_when_unnamed():
    lay = sg.build_layout({"rooms": [{"id": "a", "width_m": 10, "length_m": 10}],
                           "entry_points": [{"id": "front", "room": "a", "wall": "south", "position_frac": 0.5, "width_m": 1.2, "state": "intact"},
                                            {"id": "rear", "room": "a", "wall": "north", "position_frac": 0.5, "width_m": 1.2, "state": "forced"}],
                           "key_locations": [{"id": "near_front", "room": "a", "position_frac": [0.5, 0.1]}]}, set())
    plan = sg.plan_scenario([{"node_id": "exterior"}, {"node_id": "near_front", "dt_sec_estimate": 90}], lay)
    first = plan["actors"][0]["segments"][0]
    assert first["pos"][2] > 0, "should start outside the forced rear door"
    assert sg.validate_plan(plan, lay)["is_physically_possible"]


def test_locked_door_rule():
    raw = {"rooms": [{"id": "a", "width_m": 8, "length_m": 8}, {"id": "b", "width_m": 6, "length_m": 6, "attach": {"to": "a", "wall": "east"}}],
           "entry_points": [{"id": "front", "room": "a", "wall": "south", "position_frac": 0.5, "width_m": 1.2, "state": "open"}],
           "connections": [{"id": "vault", "room_a": "a", "room_b": "b", "position_frac": 0.5, "width_m": 1.0, "state": "locked"}],
           "key_locations": [{"id": "inside", "room": "b", "position_frac": [0.5, 0.5]}]}
    lay = sg.build_layout(raw, set())
    walk_in = [{"node_id": "exterior"}, {"node_id": "inside", "dt_sec_estimate": 10}]
    bad = sg.validate_plan(sg.plan_scenario(walk_in, lay), lay)
    assert any(v["code"] == "locked_door_passed" for v in bad["violations"]) and not bad["is_physically_possible"]
    for action in ("damage", "unlock", "open"):
        good = sg.plan_scenario([{"node_id": "exterior"}, {"node_id": "vault", "action": action, "dt_sec_estimate": 10}, {"node_id": "inside", "dt_sec_estimate": 10}], lay)
        assert sg.validate_plan(good, lay)["is_physically_possible"], action
    steps = [{"actor": "a", "node_id": "exterior"}, {"actor": "a", "node_id": "vault", "action": "unlock", "dt_sec_estimate": 5},
             {"actor": "b", "node_id": "exterior"}, {"actor": "b", "node_id": "inside"}]
    late = sg.plan_scenario(steps, lay, [{"id": "a"}, {"id": "b", "start_offset_s": 120}])
    assert not any(v["code"] == "locked_door_passed" for v in sg.validate_plan(late, lay)["violations"]), "another person may unlock it first"
    early = sg.plan_scenario(steps, lay, [{"id": "a", "start_offset_s": 200}, {"id": "b"}])
    assert any(v["code"] == "locked_door_passed" for v in sg.validate_plan(early, lay)["violations"])


def test_stairs_between_floors():
    raw = {"rooms": [{"id": "g", "width_m": 8, "length_m": 8}, {"id": "u", "width_m": 8, "length_m": 8, "attach": {"to": "g", "wall": "above"}}],
           "entry_points": [{"id": "front", "room": "g", "wall": "south", "position_frac": 0.5, "width_m": 1.2}],
           "connections": [{"id": "st", "kind": "stairs", "room_a": "g", "room_b": "u", "position_frac": [0.8, 0.8], "width_m": 1.0}],
           "key_locations": [{"id": "bedroom", "room": "u", "position_frac": [0.2, 0.2]}]}
    lay = sg.build_layout(raw, set())
    plan = sg.plan_scenario([{"node_id": "exterior"}, {"node_id": "bedroom", "dt_sec_estimate": 20}, {"node_id": "exterior", "action": "flee"}], lay)
    val = sg.validate_plan(plan, lay)
    assert val["is_physically_possible"], val["violations"]
    segs = plan["actors"][0]["segments"]
    up = [s for s in segs if s["kind"] == "dwell" and s["node_id"] == "bedroom"][0]
    assert up["pos"][1] > 2.5, "person stands on the upper floor"
    assert any("stairs" in s.get("leg_kinds", []) for s in segs if s["kind"] == "transit")
    assert any("uses the stairs" in n for s in segs for n in s.get("routing_notes", []))


def test_outdoor_object_and_place():
    lay = sg.build_layout({"rooms": [{"id": "a", "width_m": 8, "length_m": 8}],
                           "entry_points": [{"id": "rear", "room": "a", "wall": "north", "position_frac": 0.5, "width_m": 1.2}],
                           "outdoor_objects": [{"id": "van", "near": "rear", "distance_m": 4, "lateral_m": 2, "footprint_m": [2, 5], "kind": "vehicle", "height_m": 2}],
                           "key_locations": [{"id": "bin", "room": "outside", "near": "rear", "distance_m": 3, "lateral_m": -4}]}, set())
    assert lay["outdoor_objects"][0]["room"] == "outside" and lay["key_locations"][0]["room"] == "outside"
    plan = sg.plan_scenario([{"node_id": "bin", "dt_sec_estimate": 5}, {"node_id": "van", "action": "look"}, {"node_id": "rear", "action": "enter"}], lay)
    assert sg.validate_plan(plan, lay)["is_physically_possible"]


def test_l_shaped_building_outdoor_route_goes_around():
    raw = {"rooms": [{"id": "a", "width_m": 10, "length_m": 10}, {"id": "b", "width_m": 10, "length_m": 10, "attach": {"to": "a", "wall": "east", "align_frac": 1.0}}],
           "entry_points": [{"id": "w", "room": "a", "wall": "west", "position_frac": 0.5, "width_m": 1.2}, {"id": "e", "room": "b", "wall": "east", "position_frac": 0.5, "width_m": 1.2}]}
    lay = sg.build_layout(raw, set())
    plan = sg.plan_scenario([{"node_id": "w", "action": "enter"}, {"node_id": "exterior"}, {"node_id": "e", "action": "enter"}], lay)
    assert sg.validate_plan(plan, lay)["is_physically_possible"]


# ---------------------------------------------------------------- line of sight

def sight_layout():
    return sg.build_layout({
        "rooms": [{"id": "hall", "width_m": 12, "length_m": 8}, {"id": "back", "width_m": 6, "length_m": 8, "attach": {"to": "hall", "wall": "east", "align_frac": 0.5}}],
        "entry_points": [{"id": "front", "room": "hall", "wall": "south", "position_frac": 0.5, "width_m": 1.4}],
        "connections": [{"id": "inner", "room_a": "hall", "room_b": "back", "position_frac": 0.5, "width_m": 1.2}],
        "fixtures": [{"id": "tall", "room": "hall", "position_frac": [0.5, 0.5], "footprint_m": [0.8, 0.8], "height_m": 2.0},
                     {"id": "low", "room": "hall", "position_frac": [0.2, 0.5], "footprint_m": [0.8, 0.8], "height_m": 0.5}],
        "key_locations": [{"id": "inback", "room": "back", "position_frac": [0.5, 0.15]}],
        "observers": [{"id": "cam", "kind": "camera", "room": "hall", "position_frac": [0.0, 0.0], "facing_toward": "inner", "fov_deg": 120, "range_m": 30}],
    }, set())


def test_camera_sees_open_floor_but_not_through_walls_or_tall_furniture():
    lay = sight_layout()
    sc = sg.get_scene(lay)
    cam = lay["observers"][0]
    hall = lay["rooms"][0]["rect"]
    ok, why = sc.visible(cam, [hall[0] + 3, 0.0, hall[2] + 3], 0.0)
    assert ok, why
    back = lay["rooms"][1]["rect"]
    ok, why = sc.visible(cam, [back[0] + 3, 0.0, back[2] + 1], 0.0)
    assert not ok and "wall" in why
    tall = lay["fixtures"][0]["pos"]
    dx, dz = tall[0] - cam["pos"][0], tall[2] - cam["pos"][2]
    behind = [tall[0] + dx * 0.15, 0.0, tall[2] + dz * 0.15]
    ok, why = sc.visible(cam, behind, 0.0)
    assert not ok


def test_camera_range_and_field_of_view():
    lay = sight_layout()
    sc = sg.get_scene(lay)
    cam = dict(lay["observers"][0])
    cam["range_m"] = 2.0
    assert not sc.visible(cam, [cam["pos"][0] + 6, 0.0, cam["pos"][2] + 6], 0.0)[0]
    cam = dict(lay["observers"][0])
    cam["fov_deg"] = 20.0
    cam["yaw"] = cam["yaw"] + math.pi
    assert not sc.visible(cam, [cam["pos"][0] + 3, 0.0, cam["pos"][2] + 3], 0.0)[0]


def test_claimed_sighting_blocked_by_wall_is_a_violation():
    lay = sight_layout()
    backroom = [{"node_id": "exterior"}, {"node_id": "front", "dt_sec_estimate": 5}, {"node_id": "inback", "action": "search", "dt_sec_estimate": 20, "observed_by": ["cam"]}]
    val = sg.validate_plan(sg.plan_scenario(backroom, lay), lay)
    assert any(v["code"] == "not_visible" for v in val["violations"]) and not val["is_physically_possible"]


def test_unobserved_room_is_a_caution():
    lay = sg.build_layout({"rooms": [{"id": "a", "width_m": 8, "length_m": 8}, {"id": "dark", "width_m": 5, "length_m": 5, "observed": False, "attach": {"to": "a", "wall": "east"}}],
                           "entry_points": [{"id": "d", "room": "a", "wall": "south", "position_frac": 0.5, "width_m": 1.2}],
                           "connections": [{"id": "ad", "room_a": "a", "room_b": "dark", "width_m": 1.0}]}, set())
    plan = sg.plan_scenario([{"node_id": "exterior"}, {"node_id": "dark", "dt_sec_estimate": 10}], lay)
    val = sg.validate_plan(plan, lay)
    assert val["is_physically_possible"] and any("does not describe" in w for w in val["warnings"])


def test_people_meeting_in_the_same_spot_is_a_caution_not_an_error():
    lay = shop()
    steps = [{"actor": "a", "node_id": "exterior"}, {"actor": "a", "node_id": "till", "dt_sec_estimate": 30},
             {"actor": "b", "node_id": "exterior"}, {"actor": "b", "node_id": "till", "dt_sec_estimate": 30}]
    val = sg.validate_plan(sg.plan_scenario(steps, lay, [{"id": "a"}, {"id": "b"}]), lay)
    assert val["is_physically_possible"] and any("meet or collide" in w for w in val["warnings"])


def test_config_snapshot_records_every_tunable():
    snap = sg.config_snapshot()
    assert snap["engine_version"] == sg.ENGINE_VERSION and snap["walk_speed_mps"] == sg.CONFIG["walk_speed_mps"] and len(snap) > 20


def test_places_outside_are_never_inside_the_building():
    """Found with the live model: a witness 'outside' with a sideways offset landed inside the building."""
    lay = sg.build_layout({"rooms": [{"id": "a", "width_m": 8, "length_m": 8}, {"id": "b", "width_m": 8, "length_m": 8, "attach": {"to": "a", "wall": "east"}}],
                           "entry_points": [{"id": "d", "room": "a", "wall": "south", "position_frac": 0.5, "width_m": 1.2}],
                           "key_locations": [{"id": "k", "room": "outside", "near": "d", "distance_m": 0.6, "lateral_m": 12}],
                           "observers": [{"id": "guard", "kind": "witness", "room": "outside", "near": "d", "distance_m": 0.6, "lateral_m": 9}]}, set())
    sc = sg.get_scene(lay)
    for n in lay["key_locations"] + lay["observers"]:
        assert not any(sg._strictly_in_rect(n["pos"], r) for r in sc.outer_rects), n["id"]
        assert n["reachable"], n["id"]
    plan = sg.plan_scenario([{"node_id": "exterior"}, {"node_id": "guard", "dt_sec_estimate": 10}], lay)
    assert sg.validate_plan(plan, lay)["is_physically_possible"]


def test_regression_last_hop_does_not_clip_an_obstacle_corner():
    """Found by the 2,000-scene stress run (seed 40225): the final hop from the last grid cell to the
    exact stop point cut the corner of a neighbouring piece of furniture."""
    rng = random.Random(40225)
    lay = sg.build_layout(random_raw(rng), set())
    steps, actors = random_steps(rng, lay)
    val = sg.validate_plan(sg.plan_scenario(steps, lay, actors), lay)
    assert not (blocked(val) and not [v for v in val["violations"] if v["code"] in DISCLOSED])


def test_shelf_running_across_a_door_is_cut_back_not_left_blocking():
    """A real model layout put a 3.5 m shelf along the wall that holds the only door into a room,
    which made that room unreachable and sank every scenario. The shelf must be cut back and say so."""
    src = json.loads((Path(__file__).parent / "data" / "blocked_door_source.json").read_text(encoding="utf-8"))
    lay = sg.build_layout(src, set())
    assert all(o["reachable"] for o in lay["openings"])
    assert not any("not reachable from outside" in w for w in lay["warnings"])
    shelf = next(f for f in lay["fixtures"] if f["id"] == "dispensary_shelving")
    assert shelf["adjusted"] and any("cut back" in n for n in shelf["adjust_notes"])
    assert any("dispensary_shelving" in w and "cut back" in w for w in lay["warnings"])


def test_a_witness_with_a_known_position_stands_there_not_at_the_nearest_door():
    """'Outside' for a person whose own position is in the evidence must mean that position. A real run drew
    a watchman at a kiosk 20 m away standing right beside the intruder at the rear door."""
    raw = {"rooms": [{"id": "shop", "width_m": 8, "length_m": 6}],
           "entry_points": [{"id": "rear", "room": "shop", "wall": "north", "position_frac": 0.5, "width_m": 1.5, "state": "forced"}],
           "observers": [{"id": "witness_person_8", "kind": "witness", "room": "outside", "label": "K. Sundaram night watchman at main security kiosk",
                          "near": "rear", "distance_m": 22, "lateral_m": -9, "fov_deg": 120, "range_m": 30}]}
    lay = sg.build_layout(raw, set())
    spot = next(o for o in lay["observers"] if o["id"] == "witness_person_8")
    door = next(o for o in lay["openings"] if o["id"] == "rear")
    plan = sg.plan_scenario(
        [{"actor": "intruder", "node_id": "exterior", "action": "approach", "dt_sec_estimate": 5},
         {"actor": "person_8_witness", "node_id": "exterior", "action": "look", "dt_sec_estimate": 10},
         {"actor": "intruder", "node_id": "rear", "action": "damage", "dt_sec_estimate": 20}],
        lay, [{"id": "intruder", "label": "Intruder"}, {"id": "person_8_witness", "label": "K. Sundaram night watchman", "role": "witness"}])
    w = next(a for a in plan["actors"] if a["id"] == "person_8_witness")
    pos = w["segments"][0]["pos"]
    assert math.hypot(pos[0] - spot["stand_pos"][0], pos[2] - spot["stand_pos"][2]) < 0.5
    assert math.hypot(pos[0] - door["gap_pos"][0], pos[2] - door["gap_pos"][2]) > 10
    # a person with no position of their own still goes to the nearest door as before
    plan2 = sg.plan_scenario([{"actor": "x", "node_id": "exterior", "action": "approach", "dt_sec_estimate": 5}, {"actor": "x", "node_id": "rear", "action": "look", "dt_sec_estimate": 5}], lay, [{"id": "x", "label": "Passer-by"}])
    p2 = plan2["actors"][0]["segments"][0]["pos"]
    assert math.hypot(p2[0] - door["outside_pos"][0], p2[2] - door["outside_pos"][2]) < 0.5
