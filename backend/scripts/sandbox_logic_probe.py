"""Runs deliberately illogical scenarios through the engine and prints which are rejected, which get a caution and which pass."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging; logging.disable(logging.WARNING)
from pipeline import sandbox_geometry as sg

RAW = {
    "rooms": [{"id": "shop", "width_m": 8, "length_m": 6}, {"id": "store", "width_m": 6, "length_m": 5, "attach": {"to": "shop", "wall": "north", "align_frac": 0.2}}],
    "entry_points": [
        {"id": "front", "room": "shop", "wall": "south", "position_frac": 0.5, "width_m": 1.4, "state": "locked"},
        {"id": "rear", "room": "store", "wall": "north", "position_frac": 0.5, "width_m": 1.6, "state": "intact"},
    ],
    "connections": [{"id": "inner", "room_a": "shop", "room_b": "store", "position_frac": 0.5, "width_m": 1.0, "state": "open"}],
    "fixtures": [{"id": "till", "room": "shop", "position_frac": [0.5, 0.4], "footprint_m": [2, 0.7], "height_m": 1.0},
                 {"id": "safe", "room": "store", "position_frac": [0.5, 0.7], "footprint_m": [0.8, 0.6], "height_m": 1.0}],
    "key_locations": [{"id": "cash", "room": "shop", "position_frac": [0.5, 0.4]}],
    "observers": [{"id": "cam", "kind": "camera", "room": "shop", "position_frac": [0.05, 0.05], "facing_toward": "till", "fov_deg": 90, "range_m": 10}],
}
lay = sg.build_layout(RAW, set())
A = [{"id": "a", "label": "Thief", "role": "suspect"}, {"id": "b", "label": "Other", "role": "suspect"}, {"id": "v", "label": "Victim", "role": "victim"}]


def S(actor, node, action, dt=10, **kw):
    return {"actor": actor, "node_id": node, "action": action, "dt_sec_estimate": dt, "narrative": "", **kw}


def run(name, steps, actors=A):
    plan = sg.plan_scenario(steps, lay, actors)
    val = sg.validate_plan(plan, lay)
    codes = sorted({v["code"] for v in val["violations"]})
    warns = [w[:90] for w in val["warnings"]][:2]
    print(f"{name:62s} -> {'REJECTED ' + ','.join(codes) if codes else 'accepted'}" + (f" | cautions: {warns}" if warns else ""))


lay_locked = sg.build_layout({**RAW, "connections": [{**RAW["connections"][0], "state": "locked"}]}, set())
lay_open = lay
lay = lay_locked
run("walks through a LOCKED inner door before anyone unlocks it", [S("a", "till", "search"), S("a", "safe", "search"), S("a", "till", "search")])
lay = lay_open
run("same, but unlocks it first", [S("a", "exterior", "approach"), S("a", "rear", "damage", effects=[{"target": "rear", "state": "forced"}]), S("a", "inner", "unlock", effects=[{"target": "inner", "state": "unlocked"}]), S("a", "till", "search")])
run("walks through the intact (closed) rear door with no 'open' step", [S("a", "exterior", "approach"), S("a", "safe", "search"), S("a", "exterior", "flee")])
run("takes an item twice with nothing put down between", [S("a", "till", "take_item", item="cash"), S("a", "safe", "take_item", item="jewels")])
run("drops an item it never picked up", [S("a", "till", "drop_item", item="knife"), S("a", "safe", "search")])
run("hands something over while the two people are in different rooms", [S("a", "till", "hand_over"), S("b", "safe", "receive")])
run("closes a door that was never opened", [S("a", "exterior", "approach"), S("a", "front", "close"), S("a", "till", "search")])
run("victim lies down, then walks away with no getting up", [S("v", "till", "lie_down"), S("v", "safe", "move"), S("v", "till", "stand")])
run("two people stand at exactly the same spot at the same time", [S("a", "till", "search", 30), S("b", "till", "search", 30)])
run("camera 'sees' a step behind a wall (store) it cannot see into", [S("a", "till", "search"), S("a", "safe", "take_item", observed_by=["cam"], item="x")])
run("search the safe 1 second after crossing the building", [S("a", "till", "search", 1), S("a", "safe", "search", 1)])
run("uses a crowbar to force a door but never carried a tool", [S("a", "exterior", "approach"), S("a", "rear", "damage", effects=[{"target": "rear", "state": "forced"}]), S("a", "till", "search")])
run("an action at a place that is not in the scene", [S("a", "till", "search"), S("a", "basement_vault", "search"), S("a", "safe", "search")])
