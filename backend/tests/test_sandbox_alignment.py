"""People's timelines are put on the evidence clock, so a witness who hears something at 02:21 and a suspect who acts at 02:23 are not drawn an hour apart."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from test_sandbox_api import layout_reply  # noqa: E402
from pipeline import sandbox, sandbox_geometry as sg  # noqa: E402

LAY = sg.build_layout(layout_reply(), set())


def obs(i, t, text="x"):
    return {"observation_id": f"OBS-{i}", "description": text, "extracted_time": t, "classification": "fact", "source_evidence_id": "EV-1"}


EV = {"evidence_items": [{"evidence_id": "EV-1", "filename": "a.txt", "evidence_type": "text_document"}],
      "observations": [obs(1, "02:21", "heard screeching"), obs(2, "02:23", "forced breach"), obs(3, "02:30", "took cash"), obs(4, "01:15", "closed up")],
      "entities": [], "conflicts": [], "relationships": [], "timeline": []}


def S(actor, node, action, dt=10, refs=None, **kw):
    return {"actor": actor, "node_id": node, "action": action, "dt_sec_estimate": dt, "narrative": f"{actor} {action}", "evidence_refs": refs or [], **kw}


ACT = [{"id": "s", "label": "Suspect", "role": "suspect", "start_offset_s": 3900}, {"id": "w", "label": "Guard", "role": "witness"}]
STEPS = [S("s", "exterior", "approach", 5), S("s", "rear", "damage", 20, ["OBS-2"], effects=[{"target": "rear", "state": "forced"}]), S("s", "till", "take_item", 15, ["OBS-3"], item="cash"),
         S("w", "exterior", "look", 10, ["OBS-1"]), S("w", "front", "look", 10)]


def origin(plan, aid, ref_obs):
    secs = {"OBS-1": 2 * 3600 + 21 * 60, "OBS-2": 2 * 3600 + 23 * 60, "OBS-3": 2 * 3600 + 30 * 60}
    a = next(x for x in plan["actors"] if x["id"] == aid)
    st = next(s for s in a["steps"] if ref_obs in s["evidence_refs"])
    return secs[ref_obs] - st["arrive_s"]


def test_the_witness_is_moved_onto_the_suspects_clock():
    acts, info = sandbox._align_on_clock(STEPS, ACT, LAY, EV)
    assert info["applied"] and info["reference"]
    plan = sg.plan_scenario(STEPS, LAY, acts)
    suspect_avg = (origin(plan, "s", "OBS-2") + origin(plan, "s", "OBS-3")) / 2
    assert abs(suspect_avg - origin(plan, "w", "OBS-1")) < 2.0     # one shared clock now
    before = sg.plan_scenario(STEPS, LAY, ACT)
    assert abs(origin(before, "s", "OBS-2") - origin(before, "w", "OBS-1")) > 3000   # it was about an hour apart


def test_nobody_is_ever_moved_before_time_zero():
    acts, _ = sandbox._align_on_clock(STEPS, ACT, LAY, EV)
    assert all(a["start_offset_s"] >= 0 for a in acts)


def test_people_whose_clocks_already_agree_are_left_alone():
    steps = [S("s", "exterior", "approach", 5), S("s", "rear", "damage", 20, ["OBS-2"]), S("w", "exterior", "look", 10, ["OBS-1"]), S("w", "front", "look", 10)]
    acts = [{"id": "s", "label": "Suspect", "role": "suspect", "start_offset_s": 0}, {"id": "w", "label": "Guard", "role": "witness", "start_offset_s": 0}]
    plan = sg.plan_scenario(steps, LAY, acts)
    spread = abs(origin(plan, "s", "OBS-2") - origin(plan, "w", "OBS-1"))
    out, info = sandbox._align_on_clock(steps, acts, LAY, EV)
    if spread < sandbox.ALIGN_MIN_SPREAD_S:
        assert not info["applied"] and out == acts


def test_a_person_with_no_timed_evidence_is_not_moved_and_is_named():
    steps = [S("s", "exterior", "approach", 5), S("s", "rear", "damage", 20, ["OBS-2"]), S("s", "till", "take_item", 15, ["OBS-3"], item="cash"),
             S("w", "exterior", "look", 10, ["OBS-1"]), S("w", "front", "look", 10), S("v", "till", "look", 10), S("v", "safe", "look", 10)]
    acts = ACT + [{"id": "v", "label": "Owner", "role": "victim", "start_offset_s": 55}]
    out, info = sandbox._align_on_clock(steps, acts, LAY, EV)
    assert info["applied"] and info["unaligned"] == ["Owner"]
    assert next(a for a in out if a["id"] == "v")["start_offset_s"] == 55


def test_one_person_or_no_timed_evidence_changes_nothing():
    assert sandbox._align_on_clock(STEPS[:3], ACT[:1], LAY, EV)[1]["applied"] is False
    untimed = [S("s", "exterior", "approach", 5), S("s", "rear", "damage", 20), S("w", "exterior", "look", 10), S("w", "front", "look", 10)]
    assert sandbox._align_on_clock(untimed, ACT, LAY, EV)[1]["applied"] is False


def test_the_built_scenario_says_what_was_done():
    raw = {"title": "T", "hypothesis_summary": "s", "plausibility_estimate": 60, "actors": ACT, "steps": STEPS,
           "supporting_facts": [{"text": "forced", "refs": ["OBS-2"]}], "contradicted_points": []}
    scn = sandbox._build_scenario(raw, LAY, EV, sandbox._scenario_context(EV))
    assert scn["time_alignment"]["applied"] and any("put on the evidence clock" in w for w in scn["validation"]["warnings"])
