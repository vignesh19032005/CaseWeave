"""Builds a synthetic 3-floor, 4-person case (cellar, shop, flat, two staircases, camera, witness, van) with a FAKE model and saves the
resulting state as a JSON fixture for the browser tests. No model quota, no network.

  python scripts/sandbox_make_multifloor.py out.json
"""
import json, os, sys, uuid
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BACKEND); sys.path.insert(0, BACKEND)
import logging; logging.disable(logging.WARNING)
from fastapi.testclient import TestClient
import api, auth
from db import get_conn
from pipeline import sandbox

CASE = "CW-MF-" + uuid.uuid4().hex[:5]
api.limiter.enabled = False
api.app.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "U", "username": "demo-admin", "role": "admin"}

LAYOUT = {
    "scene_assessment": {"physical_scene_supported": True, "reason": "A shop with a flat above and a cellar below."},
    "rooms": [
        {"id": "shop", "label": "Shop floor", "width_m": 9, "length_m": 7, "dimensions_basis": "stated", "evidence_refs": ["OBS-M1"], "basis": "stated"},
        {"id": "office", "label": "Back office", "width_m": 4, "length_m": 4, "attach": {"to": "shop", "wall": "north", "align_frac": 0.1}, "basis": "inferred"},
        {"id": "flat", "label": "Flat above", "width_m": 9, "length_m": 7, "height_m": 2.7, "attach": {"to": "shop", "wall": "above"}, "basis": "stated", "evidence_refs": ["OBS-M3"]},
        {"id": "bed", "label": "Bedroom", "width_m": 4, "length_m": 4, "attach": {"to": "flat", "wall": "north", "align_frac": 0.1}, "basis": "inferred"},
        {"id": "cellar", "label": "Cellar", "width_m": 6, "length_m": 5, "attach": {"to": "shop", "wall": "below"}, "basis": "assumed"},
    ],
    "entry_points": [
        {"id": "front", "label": "Front door", "room": "shop", "wall": "south", "position_frac": 0.5, "width_m": 1.4, "state": "intact", "basis": "stated", "evidence_refs": ["OBS-M1"]},
        {"id": "side", "label": "Side window door", "room": "office", "wall": "east", "position_frac": 0.5, "width_m": 1.0, "state": "forced", "basis": "stated", "evidence_refs": ["OBS-M2"]},
        {"id": "balcony", "label": "Balcony door", "room": "flat", "wall": "south", "position_frac": 0.7, "width_m": 1.0, "state": "locked", "basis": "inferred"},
    ],
    "connections": [
        {"id": "d_shop_office", "label": "Office door", "room_a": "shop", "room_b": "office", "position_frac": 0.5, "width_m": 1.0, "state": "open"},
        {"id": "stairs_up", "label": "Staircase to flat", "kind": "stairs", "room_a": "shop", "room_b": "flat", "position_frac": [0.85, 0.85], "width_m": 1.0, "state": "open"},
        {"id": "stairs_down", "label": "Cellar steps", "kind": "stairs", "room_a": "shop", "room_b": "cellar", "position_frac": [0.1, 0.9], "width_m": 1.0, "state": "open"},
        {"id": "d_flat_bed", "label": "Bedroom door", "room_a": "flat", "room_b": "bed", "position_frac": 0.5, "width_m": 0.9, "state": "intact"},
    ],
    "fixtures": [
        {"id": "counter", "label": "Sales counter", "room": "shop", "category": "counter", "position_frac": [0.5, 0.45], "footprint_m": [3, 0.8], "height_m": 1.0, "basis": "stated", "evidence_refs": ["OBS-M1"]},
        {"id": "safe", "label": "Wall safe", "room": "office", "category": "safe", "position_frac": [0.5, 0.8], "footprint_m": [0.8, 0.6], "height_m": 1.2, "basis": "stated", "evidence_refs": ["OBS-M2"]},
        {"id": "bedbed", "label": "Double bed", "room": "bed", "category": "bed", "position_frac": [0.5, 0.5], "footprint_m": [1.8, 2.0], "height_m": 0.6, "basis": "inferred"},
        {"id": "sofa", "label": "Sofa", "room": "flat", "category": "chair", "position_frac": [0.3, 0.4], "footprint_m": [2, 0.9], "height_m": 0.9},
        {"id": "shelf", "label": "Wine rack", "room": "cellar", "category": "shelf", "position_frac": [0.5, 0.2], "footprint_m": [3, 0.5], "height_m": 1.8},
    ],
    "key_locations": [
        {"id": "safe_spot", "label": "Safe opened", "room": "office", "position_frac": [0.5, 0.7], "significance": "safe emptied", "basis": "stated", "evidence_refs": ["OBS-M2"]},
        {"id": "victim_spot", "label": "Where the occupant was found", "room": "bed", "position_frac": [0.5, 0.35], "significance": "occupant found injured", "basis": "stated", "evidence_refs": ["OBS-M3"]},
    ],
    "outdoor_objects": [{"id": "van", "label": "White van", "near": "front", "distance_m": 5, "lateral_m": 3, "footprint_m": [2, 5], "kind": "vehicle", "height_m": 2, "basis": "stated", "evidence_refs": ["OBS-M4"]}],
    "observers": [
        {"id": "cam_shop", "label": "Shop CCTV", "kind": "camera", "room": "shop", "position_frac": [0.05, 0.95], "facing_toward": "counter", "fov_deg": 110, "range_m": 12, "basis": "stated", "evidence_refs": ["OBS-M1"]},
        {"id": "wit_flat", "label": "Neighbour at window", "kind": "witness", "room": "flat", "position_frac": [0.8, 0.9], "facing_toward": "balcony", "fov_deg": 120, "range_m": 15},
    ],
    "notes": "synthetic multi-floor test",
}

def sc(title, actors, steps, est=70):
    return {"title": title, "hypothesis_summary": f"{title}: synthetic multi-floor scenario.", "plausibility_estimate": est, "actors": actors,
            "supporting_facts": [{"text": "Side door forced", "refs": ["OBS-M2"]}], "contradicted_points": [], "steps": steps}
S = lambda actor, node, action, dt, narr, **kw: {"actor": actor, "node_id": node, "action": action, "dt_sec_estimate": dt, "narrative": narr, **kw}
ACT = [{"id": "a", "label": "Intruder A", "role": "suspect"}, {"id": "b", "label": "Intruder B", "role": "suspect"},
       {"id": "c", "label": "Occupant", "role": "victim"}, {"id": "d", "label": "Neighbour", "role": "witness"}]
REPLY = {"scenarios": [
    sc("Two intruders, one goes upstairs", ACT, [
        S("a", "exterior", "approach", 5, "Arrives by van"), S("a", "side", "damage", 20, "Forces the side door", evidence_refs=["OBS-M2"], effects=[{"target": "side", "state": "forced"}]),
        S("a", "safe_spot", "take_item", 30, "Empties the safe", evidence_refs=["OBS-M2"], item="cash"),
        S("a", "stairs_up", "move", 5, "Goes up"), S("a", "victim_spot", "struggle", 15, "Confronts the occupant", evidence_refs=["OBS-M3"]),
        S("a", "exterior", "flee", 5, "Leaves"),
        S("b", "exterior", "wait", 5, "Waits in the van"), S("b", "counter", "search", 20, "Searches the counter", evidence_refs=["OBS-M1"], observed_by=["cam_shop"]),
        S("c", "victim_spot", "lie_down", 30, "Occupant lies injured", evidence_refs=["OBS-M3"]),
        S("d", "wit_flat", "look", 30, "Neighbour watches the balcony"),
    ]),
    sc("Single intruder uses the cellar", [ACT[0], ACT[2]], [
        S("a", "side", "damage", 15, "Forces the side door", evidence_refs=["OBS-M2"]), S("a", "shelf", "search", 20, "Searches the cellar"),
        S("a", "safe_spot", "take_item", 20, "Takes the cash", evidence_refs=["OBS-M2"], item="cash"),
        S("c", "victim_spot", "sit", 20, "Occupant sits on the bed")]),
    sc("Intruder enters through the front", [ACT[0]], [
        S("a", "front", "open", 8, "Opens the front door", evidence_refs=["OBS-M1"]), S("a", "counter", "search", 20, "Searches the counter", evidence_refs=["OBS-M1"])], 40),
]}

class Fake:
    @staticmethod
    def fake(system, prompt, max_tokens=2048, timeout=None):
        if "scene analyst" in system: out = LAYOUT
        elif "exactly 3 DIFFERENT" in system: out = REPLY
        elif "senior forensic examiner" in system: out = {"questions": []}
        else: out = REPLY["scenarios"][0]
        return {"provider": "fake", "model": "fake-1", "parsed": out, "raw": json.dumps(out)}

conn = get_conn()
conn.execute("INSERT INTO cases (case_id, title, created_at) VALUES (?,?,?)", (CASE, "Synthetic 3-floor test", "now"))
conn.execute("INSERT INTO evidence_items (evidence_id, case_id, filename, file_hash, evidence_type, status) VALUES (?,?,?,?,?,?)", ("EV-" + CASE, CASE, "cctv.mp4", "h", "video", "done"))
for oid, text, t in (("OBS-M1", "Shop is a ground floor retail unit with a front door and counter", "23:10"), ("OBS-M2", "Side door forced and wall safe emptied", "23:20"),
                     ("OBS-M3", "Occupant of the flat above found injured in the bedroom", "23:35"), ("OBS-M4", "A white van was parked in front", None)):
    conn.execute("INSERT INTO observations (observation_id, case_id, description, classification, source_evidence_id, extracted_time) VALUES (?,?,?,?,?,?)",
                 (oid, CASE, text, "fact", "EV-" + CASE, t))
conn.commit(); conn.close()
real = sandbox.chat_json_ex; sandbox.chat_json_ex = Fake.fake
try:
    c = TestClient(api.app)
    r = c.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "full"})
    d = c.get(f"/cases/{CASE}/sandbox").json()
    print("status", d["status"], d.get("last_failure"))
    for s in d["scenarios"]:
        v = s["validation"]
        print(s["title"], "| ok", v["is_physically_possible"], "| people", [a["label"] for a in s["actors"]], "| violations", [x["message"][:90] for x in v["violations"]][:3],
              "| stairs", any("stairs" in sg.get("leg_kinds", []) for a in s["plan"]["actors"] for sg in a["segments"]))
    L = d["run"]["layout"]; print("levels", L["levels"], "rooms", [(r["id"], r["level"]) for r in L["rooms"]])
    json.dump(d, open(sys.argv[1] if len(sys.argv) > 1 else "multifloor_state.json", "w", encoding="utf-8"))
finally:
    sandbox.chat_json_ex = real
    conn = get_conn()
    for t in ("sandbox_scenarios", "sandbox_runs", "case_narratives", "observations", "entities", "evidence_items", "cases"):
        conn.execute(f"DELETE FROM {t} WHERE case_id=?", (CASE,))
    conn.commit(); conn.close()
