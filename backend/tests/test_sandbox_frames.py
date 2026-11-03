"""The frames the reviewer sees: the right moments, within a cap, drawn from the same truth as the simulation."""
import io
import json
import sys
from pathlib import Path

from PIL import Image

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from pipeline import sandbox_frames as fr  # noqa: E402
from pipeline import sandbox_geometry as sg  # noqa: E402

RAW = json.loads((Path(__file__).parent / "data" / "blocked_door_source.json").read_text(encoding="utf-8"))
LAY = sg.build_layout(RAW, set())


def S(actor, node, action, dt=10, **kw):
    return {"actor": actor, "node_id": node, "action": action, "dt_sec_estimate": dt, "narrative": f"{actor} {action}", **kw}


def scenario(steps, actors):
    plan = sg.plan_scenario(steps, LAY, actors)
    return {"plan": plan, "time": {"clock_anchors": [{"t_model": 0.0, "sod": 8 * 3600, "observation_id": "o", "actor": actors[0]["id"]}], "anchors": []}, "title": "Test scenario"}


ACT = [{"id": "a", "label": "Thief", "role": "suspect"}, {"id": "w", "label": "Guard", "role": "witness"}]
STEPS = [S("a", "exterior", "approach"), S("a", "rear_shutter_gate_b", "damage", effects=[{"target": "rear_shutter_gate_b", "state": "forced"}]),
         S("a", "narcotics_locker", "take_item", item="drugs"), S("a", "exterior", "flee"), S("w", "exterior", "look")]


def test_the_frames_cover_start_end_every_step_every_change_and_one_overview():
    scn = scenario(STEPS, ACT)
    frames = fr.plan_frames(scn, LAY)
    kinds = [f["kind"] for f in frames]
    assert kinds.count("start") == 1 and kinds.count("end") == 1 and kinds.count("overview") == 1
    assert kinds.count("step") >= 4 and kinds.count("effect") >= 1
    assert any(f["kind"] == "before" for f in frames) and any(f["kind"] == "after" for f in frames)
    assert [f["id"] for f in frames] == [f"F{i}" for i in range(1, len(frames) + 1)]
    times = [f["t"] for f in frames if f["kind"] != "overview"]
    assert times == sorted(times)


def test_never_more_than_the_cap_and_the_required_kinds_survive_it():
    steps = []
    for i in range(14):
        steps += [S("a", "narcotics_locker", "take_item", item=f"item{i}"), S("a", "rear_shutter_gate_b", "open")]
    scn = scenario(steps, ACT[:1])
    frames = fr.plan_frames(scn, LAY)
    assert len(frames) <= fr.MAX_FRAMES
    kinds = {f["kind"] for f in frames}
    assert {"start", "end", "overview"} <= kinds


def test_a_claimed_sighting_gets_its_own_frame_from_that_observers_side():
    lay_obs = sg.build_layout({**RAW, "observers": [{"id": "cam", "kind": "camera", "room": "outside", "near": "rear_shutter_gate_b", "distance_m": 5, "lateral_m": 0, "fov_deg": 120, "range_m": 30}]}, set())
    plan = sg.plan_scenario([S("a", "exterior", "approach"), S("a", "rear_shutter_gate_b", "damage", observed_by=["cam"]), S("a", "narcotics_locker", "take_item")], lay_obs, ACT[:1])
    scn = {"plan": plan, "time": {"clock_anchors": [], "anchors": []}, "title": "T"}
    frames = fr.plan_frames(scn, lay_obs)
    sight = [f for f in frames if f["kind"] == "sighting"]
    assert sight and sight[0]["observer"] == "cam"
    png = fr.render_frame(lay_obs, scn, sight[0])
    assert Image.open(io.BytesIO(png)).size[0] >= 900


def test_every_frame_renders_to_a_real_non_blank_picture():
    scn = scenario(STEPS, ACT)
    for f in fr.plan_frames(scn, LAY):
        img = Image.open(io.BytesIO(fr.render_frame(LAY, scn, f))).convert("RGB")
        assert img.size[0] >= 900 and img.size[1] >= 600
        assert len(set(img.getdata())) > 40          # more than a flat background


def test_people_are_hollow_before_their_first_step_and_after_their_last_and_the_caption_says_so():
    scn = scenario(STEPS, ACT)
    end = next(f for f in fr.plan_frames(scn, LAY) if f["kind"] == "end")
    cap = fr.frame_caption(scn, end)
    assert "last known position after their last step" in cap and "Guard (witness)" in cap
    start = next(f for f in fr.plan_frames(scn, LAY) if f["kind"] == "start")
    assert "F1 [start]" in fr.frame_caption(scn, start)


def test_a_door_the_scenario_forces_later_is_drawn_closed_until_then():
    scn = scenario(STEPS, ACT)
    op = next(o for o in LAY["openings"] if o["id"] == "rear_shutter_gate_b")
    eff = scn["plan"]["effects"]
    t_force = next(e["t"] for e in eff if e["target"] == "rear_shutter_gate_b" and e["state"] == "forced")
    assert fr.door_state_at(op, eff, 0.0) == "intact" and fr.door_state_at(op, eff, t_force + 1) == "forced"


def test_the_clock_follows_the_cited_anchor():
    scn = scenario(STEPS, ACT)
    assert fr.clock_at(scn, 0.0) == "08:00:00" and fr.clock_at(scn, 90.0) == "08:01:30"
    assert fr.clock_at({"time": {"clock_anchors": []}}, 5.0) is None


def test_far_off_people_and_objects_become_edge_markers_not_a_tiny_building():
    lay = sg.build_layout({**RAW, "observers": [{"id": "wit", "kind": "witness", "room": "outside", "near": "rear_shutter_gate_b", "distance_m": 24, "lateral_m": -9, "fov_deg": 120, "range_m": 30}]}, set())
    scn = {"plan": sg.plan_scenario([S("a", "exterior", "approach"), S("a", "narcotics_locker", "search")], lay, ACT[:1]), "time": {"clock_anchors": [], "anchors": []}, "title": "T"}
    x0, x1, z0, z1 = fr._bounds(lay, scn)
    rooms_w = max(r["rect"][1] for r in lay["rooms"]) - min(r["rect"][0] for r in lay["rooms"])
    assert (x1 - x0) < rooms_w + 20


def test_a_door_someone_is_still_forcing_is_drawn_as_being_worked_on_not_as_closed():
    scn = scenario(STEPS, ACT)
    op = next(o for o in LAY["openings"] if o["id"] == "rear_shutter_gate_b")
    a = next(a for a in scn["plan"]["actors"] if a["id"] == "a")
    work = next(g for g in a["segments"] if g["kind"] == "dwell" and g["node_id"] == "rear_shutter_gate_b" and g["action"] == "damage")
    t_force = next(e["t"] for e in scn["plan"]["effects"] if e["target"] == "rear_shutter_gate_b")
    t_mid = (work["t0"] + work["t1"]) / 2
    if t_mid < t_force:
        assert fr.door_state_at(op, scn["plan"]["effects"], t_mid, scn["plan"]["actors"]) == "being worked on"
    assert fr.door_state_at(op, scn["plan"]["effects"], work["t0"] - 3.0, scn["plan"]["actors"]) == "intact"
    assert fr.door_state_at(op, scn["plan"]["effects"], t_force + 0.5, scn["plan"]["actors"]) == "forced"
