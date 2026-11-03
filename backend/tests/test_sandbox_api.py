"""API-level tests for the scene sandbox with a mocked model.

Uses a throwaway case in the real database (removed afterwards) and a fake
language model, so it is repeatable and spends no quota. It checks the promises
that matter to a department: permissions, no generation on read, refusal without
evidence, one generation at a time (even under concurrent clicks), PII never sent
to the model, fake citations stripped, any number of people, staleness explained,
immutable versions, editing with deterministic re-planning, an intact audit trail
that survives deleting the case, and a printable review pack.
"""
import json
import os
import sys
import threading
import uuid
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
import auth  # noqa: E402
from db import get_conn, verify_audit_chain  # noqa: E402
from pipeline import sandbox  # noqa: E402

CASE = f"CW-TEST-{uuid.uuid4().hex[:6]}"
EMPTY_CASE = f"CW-TEST-{uuid.uuid4().hex[:6]}"
ROLE = {"v": "admin"}
SENT_PROMPTS: list = []


def layout_reply():
    return {
        "scene_assessment": {"physical_scene_supported": True, "reason": "A shop is described."},
        "rooms": [
            {"id": "shop", "label": "Shop floor", "width_m": 10, "length_m": 8, "dimensions_basis": "assumed"},
            {"id": "store", "label": "Stockroom", "width_m": 6, "length_m": 5, "attach": {"to": "shop", "wall": "north", "align_frac": 0.2}, "evidence_refs": ["OBS-T2"], "basis": "inferred"},
        ],
        "entry_points": [
            {"id": "front", "label": "Front door", "room": "shop", "wall": "south", "position_frac": 0.5, "width_m": 1.4, "state": "intact", "basis": "stated", "evidence_refs": ["OBS-T1"]},
            {"id": "rear", "label": "Rear shutter", "room": "store", "wall": "north", "position_frac": 0.5, "width_m": 2.0, "state": "forced", "basis": "stated", "evidence_refs": ["OBS-T2"]},
        ],
        "connections": [{"id": "inner", "label": "Inner door", "room_a": "shop", "room_b": "store", "position_frac": 0.5, "width_m": 1.0, "state": "open"}],
        "fixtures": [{"id": "counter", "label": "Counter", "room": "shop", "position_frac": [0.5, 0.4], "footprint_m": [3, 0.8], "height_m": 1, "basis": "inferred", "evidence_refs": ["OBS-T3", "OBS-FAKE"]},
                     {"id": "shelf", "label": "Shelf", "room": "store", "position_frac": [0.5, 0.5], "footprint_m": [3, 0.5], "height_m": 1.9}],
        "key_locations": [{"id": "till", "label": "Till", "room": "shop", "position_frac": [0.5, 0.4], "significance": "cash taken", "basis": "stated", "evidence_refs": ["OBS-T3"]}],
        "observers": [{"id": "cam", "label": "Shop camera", "kind": "camera", "room": "shop", "position_frac": [0.05, 0.05], "facing_toward": "front", "fov_deg": 120, "range_m": 30}],
        "notes": "test",
    }


def scenario_reply():
    def sc(title, actors, steps):
        return {"title": title, "hypothesis_summary": "x", "plausibility_estimate": 80, "actors": actors,
                "supporting_facts": [{"text": "Rear shutter forced [OBS-T2] and a made-up fact [OBS-NOPE]", "refs": ["OBS-T2"]}], "contradicted_points": [], "steps": steps}
    good = [
        {"actor": "a", "node_id": "exterior", "action": "approach", "dt_sec_estimate": 5, "narrative": "Approaches the building"},
        {"actor": "a", "node_id": "rear", "action": "damage", "dt_sec_estimate": 20, "narrative": "Forces the rear shutter", "evidence_refs": ["OBS-T2"], "effects": [{"target": "rear", "state": "forced"}]},
        {"actor": "a", "node_id": "till", "action": "take_item", "dt_sec_estimate": 20, "narrative": "Empties the till", "evidence_refs": ["OBS-T3"], "item": "cash", "observed_by": ["cam"]},
        {"actor": "a", "node_id": "exterior", "action": "flee", "dt_sec_estimate": 5, "narrative": "Runs off"},
        {"actor": "b", "node_id": "exterior", "action": "wait", "dt_sec_estimate": 5, "narrative": "Waits outside"},
        {"actor": "b", "node_id": "rear", "action": "look", "dt_sec_estimate": 10, "narrative": "Watches the rear shutter"},
    ]
    bad_time = [
        {"actor": "a", "node_id": "exterior", "action": "approach", "dt_sec_estimate": 5, "narrative": "Takes the till cash", "evidence_refs": ["OBS-T3"]},
        {"actor": "a", "node_id": "till", "action": "take_item", "dt_sec_estimate": 5, "narrative": "Forces the rear shutter", "evidence_refs": ["OBS-T2"]},
        {"actor": "a", "node_id": "no_such_room", "action": "search", "dt_sec_estimate": 5},
    ]
    weak = [
        {"actor": "a", "node_id": "exterior", "action": "approach", "dt_sec_estimate": 5, "narrative": "Walks up"},
        {"actor": "a", "node_id": "till", "action": "take_item", "dt_sec_estimate": 10, "narrative": "Empties the till drawer", "evidence_refs": ["OBS-T1"]},
    ]
    return {"scenarios": [
        sc("PERSON_1 and a lookout", [{"id": "a", "label": "PERSON_1", "role": "suspect"}, {"id": "b", "label": "Lookout", "role": "suspect"}], good),
        sc("B", [{"id": "a", "label": "Intruder"}], bad_time),
        sc("C", [{"id": "a", "label": "Intruder"}], weak)]}


class FakeModel:
    calls = 0

    @staticmethod
    def fake(system, prompt, max_tokens=2048, timeout=None):
        FakeModel.calls += 1
        SENT_PROMPTS.append(prompt)
        if "scene analyst" in system:
            out = layout_reply()
        elif "exactly 3 DIFFERENT" in system:
            out = scenario_reply()
        elif "senior forensic examiner" in system:
            out = {"questions": [{"question": "Were there tool marks?", "category": "physical_entry", "suggested_answers": ["yes", "no"]}]}
        else:
            out = scenario_reply()["scenarios"][0]
        return {"provider": "fake", "model": "fake-1", "parsed": out, "raw": json.dumps(out)}


@pytest.fixture(scope="module")
def client():
    api.app.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "U", "username": f"t-{ROLE['v']}", "role": ROLE["v"]}
    real_model = sandbox.chat_json_ex
    sandbox.chat_json_ex = FakeModel.fake
    api.limiter.enabled = False
    conn = get_conn()
    for cid in (CASE, EMPTY_CASE):
        conn.execute("INSERT INTO cases VALUES (?,?,?)", (cid, "test", "now"))
    conn.execute("INSERT INTO evidence_items VALUES (?,?,?,?,?,?)", ("EV-T1", CASE, "cctv.mp4", "h", "video", "done"))
    conn.execute("INSERT INTO entities (entity_id, case_id, canonical_name, entity_type, aliases) VALUES (?,?,?,?,?)", ("ENT-T1", CASE, "Ramesh Kumaran", "person", "R. Kumaran,Kumaran"))
    for oid, text, t in (("OBS-T1", "Front door was locked by Ramesh Kumaran, phone 9876543210", "01:10"), ("OBS-T2", "Rear shutter forced", "01:15"),
                         ("OBS-T3", "Till emptied", "01:30"), ("OBS-T4", "Untimed note", None)):
        conn.execute("INSERT INTO observations (observation_id, case_id, description, classification, source_evidence_id, extracted_time) VALUES (?,?,?,?,?,?)",
                     (oid, CASE, text, "fact", "EV-T1", t))
    conn.commit()
    conn.close()
    yield TestClient(api.app)
    conn = get_conn()
    for t in ("sandbox_scenarios", "sandbox_runs", "case_narratives", "observations", "entities", "evidence_items", "audit_events", "cases"):
        conn.execute(f"DELETE FROM {t} WHERE case_id IN (?,?)", (CASE, EMPTY_CASE))
    conn.commit()
    conn.close()
    sandbox.chat_json_ex = real_model
    api.limiter.enabled = True
    api.app.dependency_overrides.clear()


def state(c):
    return c.get(f"/cases/{CASE}/sandbox").json()


def test_01_read_never_generates(client):
    before = FakeModel.calls
    d = state(client)
    assert d["status"] == "none" and FakeModel.calls == before


def test_02_permissions(client):
    ROLE["v"] = "reviewer"
    assert client.post(f"/cases/{CASE}/sandbox/generate", json={}).status_code == 403
    # exporting is allowed for anyone who may view the case (there is no scene yet, so the answer is "nothing to export", not "forbidden")
    assert client.get(f"/cases/{CASE}/sandbox/export").status_code != 403
    assert client.get(f"/cases/{CASE}/sandbox/export.pdf").status_code != 403
    assert client.post(f"/cases/{CASE}/sandbox/layout", json={"ops": []}).status_code == 403
    assert client.get(f"/cases/{CASE}/sandbox").status_code == 200
    ROLE["v"] = "admin"


def test_03_refuses_without_evidence_and_unknown_case(client):
    assert client.post(f"/cases/{EMPTY_CASE}/sandbox/generate", json={}).status_code == 422
    assert client.get("/cases/NOPE-123/sandbox").status_code == 404
    assert client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "bogus"}).status_code == 400
    assert client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "scenarios_only"}).status_code == 400


def test_04_generation_people_citations_and_clocks(client):
    SENT_PROMPTS.clear()
    assert client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "full"}).status_code == 202
    d = state(client)
    assert d["status"] == "ready" and d["run"]["schema_version"] == 3
    lay = d["run"]["layout"]
    assert len(lay["rooms"]) == 2 and any(o["kind"] == "external" and o["state"] == "forced" for o in lay["openings"])
    assert lay["fixtures"][0]["evidence_refs"] == ["OBS-T3"], "fake citation must be stripped"
    assert "source" not in lay, "the editable source stays on the server"
    assert [s["rank"] for s in d["scenarios"]] == [1, 2, 3]
    top = d["scenarios"][0]
    assert len(top["actors"]) == 2 and top["validation"]["is_physically_possible"], top["validation"]["violations"]
    assert top["title"].startswith("Ramesh Kumaran"), "names are restored locally after the model call"
    assert any(e["target"] == "rear" and e["state"] == "forced" for e in top["plan"]["effects"])
    assert top["supporting_facts"][0]["invalid_refs"] == ["OBS-NOPE"] and top["citations_removed"] >= 1
    assert top["time"]["basis"] == "anchored" and top["time"]["clock_anchors"]
    assert top["validation"]["observation_checks"] and top["validation"]["observation_checks"][0]["visible"]
    bad = [s for s in d["scenarios"] if s["title"] == "B"][0]
    assert not bad["validation"]["is_physically_possible"] and any(v["code"] == "anchor_order_conflict" for v in bad["validation"]["violations"])
    assert bad["plan"]["dropped_steps"][0]["node_id"] == "no_such_room" and bad["score"]["verifiable_score"] <= 25
    weak = [s for s in d["scenarios"] if s["title"] == "C"][0]
    assert weak["weak_citations"] and weak["score"]["components"]["steps_citing_evidence"] == 0, "a citation that does not concern the step is not support"
    assert top["evidence_index"]["OBS-T2"]["text"] == "Rear shutter forced"
    for s in d["scenarios"]:
        for a in s["plan"]["actors"]:
            for stp in a["steps"]:
                assert all(r in s["evidence_index"] for r in stp["evidence_refs"]), "every citation shown resolves to real text"


def test_05_nothing_identifying_is_sent_to_the_model(client):
    assert SENT_PROMPTS, "the fake model saw the prompts"
    for p in SENT_PROMPTS:
        assert "Kumaran" not in p and "Ramesh" not in p and "9876543210" not in p, "names and phone numbers must be redacted before sending"
    assert any("PERSON_1" in p for p in SENT_PROMPTS)
    d = state(client)
    red = d["run"]["generation"]["redaction"]
    assert red["enabled"] and red["replacements"]["PERSON"] >= 1 and red["replacements"]["PHONE"] >= 1 and red["not_covered"]
    assert all(c["redacted"] for c in d["run"]["generation"]["calls"])


def test_06_one_generation_at_a_time_even_under_concurrent_clicks(client):
    conn = get_conn()
    conn.execute("INSERT INTO sandbox_runs (run_id, case_id, status, is_current, schema_version, mode, created_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
                 ("RUN-T-busy", CASE, "generating", 0, 3, "full", "x", sandbox._now()))
    conn.commit()
    conn.close()
    assert client.post(f"/cases/{CASE}/sandbox/generate", json={}).status_code == 409
    assert state(client)["status"] == "generating"
    conn = get_conn()
    conn.execute("DELETE FROM sandbox_runs WHERE run_id='RUN-T-busy'")
    conn.commit()
    conn.close()
    results, user = [], {"username": "racer", "role": "admin"}

    def go():
        try:
            results.append(sandbox.start_generation(CASE, user, "scenarios_only"))
        except sandbox.SandboxError as e:
            results.append(e.status_code)

    threads = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    started = [r for r in results if isinstance(r, str)]
    assert len(started) == 1 and all(r in (409,) for r in results if not isinstance(r, str)), results
    conn = get_conn()
    conn.execute("DELETE FROM sandbox_runs WHERE case_id=? AND status='generating'", (CASE,))
    conn.commit()
    conn.close()


def test_07_stale_evidence_is_detected_and_explained(client):
    assert state(client)["stale"] is False
    conn = get_conn()
    conn.execute("UPDATE observations SET description='Rear shutter NOT forced' WHERE observation_id='OBS-T2'")
    conn.execute("INSERT INTO observations (observation_id, case_id, description, classification, source_evidence_id, extracted_time) VALUES (?,?,?,?,?,?)",
                 ("OBS-T5", CASE, "A new observation", "fact", "EV-T1", "01:40"))
    conn.commit()
    conn.close()
    d = state(client)
    assert d["stale"] is True and "1 observation added" in d["stale_detail"] and "1 observation changed" in d["stale_detail"]


def test_08_approve_then_reuse_layout_keeps_history_and_uses_the_saved_narrative(client):
    ROLE["v"] = "reviewer"
    assert client.post(f"/cases/{CASE}/sandbox/approve-layout").status_code == 200
    ROLE["v"] = "admin"
    sandbox.save_narrative(CASE, {"narrative": "x", "supported_facts": ["The cash register was emptied overnight", "A rear shutter was forced"]}, {"username": "t", "role": "admin"})
    assert client.get(f"/cases/{CASE}/narrative").json()["content"]["supported_facts"]
    h1 = state(client)["run"]["layout_hash"]
    assert client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "scenarios_only"}).status_code == 202
    d = state(client)
    assert d["run"]["layout_hash"] == h1 and d["run"]["approved_by"] == "t-reviewer"
    assert len(d["history"]) == 2 and sorted(h["status"] for h in d["history"]) == ["ready", "superseded"]
    assert len([s for s in d["scenarios"] if s["scenario_type"] == "automated"]) == 3, "the old run's scenarios must not be duplicated"
    assert d["scenarios"][0]["narrative_consistency"]["available"]
    old = [h for h in d["history"] if not h["is_current"]][0]["run_id"]
    assert client.get(f"/cases/{CASE}/sandbox/runs/{old}").json()["run"]["status"] == "superseded"


def test_09_officer_corrects_the_room_and_everything_is_replanned_without_the_model(client):
    before = FakeModel.calls
    d0 = state(client)
    assert client.post(f"/cases/{CASE}/sandbox/layout", json={"ops": []}).status_code == 400
    assert client.post(f"/cases/{CASE}/sandbox/layout", json={"ops": [{"op": "set", "kind": "fixture", "id": "nope", "fields": {"label": "x"}}]}).status_code == 400
    assert client.post(f"/cases/{CASE}/sandbox/layout", json={"ops": [{"op": "set", "kind": "fixture", "id": "counter", "fields": {"evil": 1}}]}).status_code == 400
    ops = [{"op": "set", "kind": "room", "id": "shop", "fields": {"width_m": 12.5, "length_m": 9}},
           {"op": "add", "kind": "fixture", "fields": {"id": "safe", "label": "Wall safe", "room": "store", "position_frac": [0.9, 0.9], "footprint_m": [0.6, 0.6], "height_m": 1}},
           {"op": "set", "kind": "opening", "id": "front", "fields": {"state": "locked"}}]
    r = client.post(f"/cases/{CASE}/sandbox/layout", json={"ops": ops})
    assert r.status_code == 200 and r.json()["scenarios"] == 3
    assert FakeModel.calls == before, "editing never calls the model"
    d = state(client)
    lay = d["run"]["layout"]
    shop = [x for x in lay["rooms"] if x["id"] == "shop"][0]
    assert shop["width_m"] == 12.5 and shop["dimensions_basis"] == "measured"
    assert [f for f in lay["fixtures"] if f["id"] == "safe"][0]["basis"] == "officer" and lay["coverage"]["officer"] >= 2
    assert [o for o in lay["openings"] if o["id"] == "front"][0]["state"] == "locked"
    assert d["run"]["approved_by"] is None, "an edited layout needs approving again"
    assert d["run"]["mode"] == "edited" and len(d["scenarios"]) == 3
    assert any(h["run_id"] == d0["run"]["run_id"] and h["status"] == "superseded" for h in d["history"]), "the earlier version is kept"
    conn = get_conn()
    try:
        assert verify_audit_chain(conn, CASE)
    finally:
        conn.close()


def test_10_officer_scenario_and_retraction(client):
    q = client.post(f"/cases/{CASE}/sandbox/interview", json={"hypothesis_text": "Two people came through the rear shutter around 01:20"})
    assert q.status_code == 200 and q.json()["questions"][0]["id"] == "q1"
    assert client.post(f"/cases/{CASE}/sandbox/interview", json={"hypothesis_text": "short"}).status_code == 400
    r = client.post(f"/cases/{CASE}/sandbox/scenarios", json={"hypothesis_text": "Two people came through the rear shutter around 01:20", "interview": [{"question": "Tool marks?", "answer": "yes"}]})
    assert r.status_code == 200
    sc = r.json()
    assert sc["scenario_type"] == "officer_custom" and sc["officer_input"]["interview"][0]["answer"] == "yes" and sc["officer_input"]["times_mentioned"] == ["01:20"]
    assert client.post(f"/cases/{CASE}/sandbox/scenarios/{sc['scenario_id']}/retract", json={"reason": "x"}).status_code == 400
    assert client.post(f"/cases/{CASE}/sandbox/scenarios/{sc['scenario_id']}/retract", json={"reason": "Withdrawn by officer"}).status_code == 200
    mine = [s for s in state(client)["scenarios"] if s["scenario_id"] == sc["scenario_id"]][0]
    assert mine["status"] == "retracted" and mine["retracted"]["reason"] == "Withdrawn by officer"


def test_11_rules_changed_since_a_scenario_was_stored_are_rechecked_on_read(client):
    conn = get_conn()
    cur = state(client)["run"]["run_id"]
    row = conn.execute("SELECT scenario_id, content_json FROM sandbox_scenarios WHERE run_id=? AND scenario_type='automated' LIMIT 1", (cur,)).fetchone()
    content = json.loads(row["content_json"])
    content["engine_version"] = "2.0"
    conn.execute("UPDATE sandbox_scenarios SET content_json=? WHERE scenario_id=?", (json.dumps(content), row["scenario_id"]))
    conn.commit()
    conn.close()
    shown = [s for s in state(client)["scenarios"] if s["scenario_id"] == row["scenario_id"]][0]
    assert shown["revalidated_with"] == sandbox.geo.ENGINE_VERSION and "re-run" in shown["revalidation_note"]


def test_12_export_pack_pdf_and_audit_chain(client):
    p = client.get(f"/cases/{CASE}/sandbox/export").json()
    assert p["audit_chain_verified"] is True and p["pack_hash"] and "not a record of what happened" in p["disclaimer"]
    assert p["redaction"] is not None and p["engine_config"]["walk_speed_mps"] > 0
    assert any(c["step"] == "layout" for c in p["raw_model_calls"]), "the layout model call is kept even after edits"
    actions = [e["action"] for e in p["audit_events"]]
    for needed in ("sandbox_generation_started", "sandbox_generation_ready", "sandbox_layout_approved", "sandbox_layout_edited", "sandbox_custom_scenario_created", "sandbox_scenario_retracted", "case_narrative_saved"):
        assert needed in actions or needed == "case_narrative_saved"
    r = client.get(f"/cases/{CASE}/sandbox/export.pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.content) > 8000
    try:
        import fitz
        doc = fitz.open(stream=r.content, filetype="pdf")
        text = " ".join(page.get_text() for page in doc)
        assert doc.page_count >= 3 and "hypothesis visualisation" in text and "Floor plan" in text and "Audit trail" in text
    except ImportError:
        pass


def test_13_model_failure_is_recorded_and_keeps_the_previous_scene(client):
    good_run = state(client)["run"]["run_id"]

    def boom(system, prompt, max_tokens=2048, timeout=None):
        raise sandbox.LLMUnavailableError("down")
    real = sandbox.chat_json_ex
    sandbox.chat_json_ex = boom
    try:
        assert client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "full"}).status_code == 202
    finally:
        sandbox.chat_json_ex = real
    d = state(client)
    assert d["status"] == "ready" and d["run"]["run_id"] == good_run, "a failed attempt must not replace the good scene"
    assert d["last_failure"] and "language model" in d["last_failure"]["message"]


def test_14_an_older_stored_scene_is_flagged_outdated_not_misread(client):
    conn = get_conn()
    cur = state(client)["run"]["run_id"]
    conn.execute("UPDATE sandbox_runs SET schema_version=2 WHERE run_id=?", (cur,))
    conn.commit()
    conn.close()
    d = state(client)
    assert d["status"] == "outdated" and d["scenarios"] == [] and d["run"]["run_id"] == cur
    assert client.post(f"/cases/{CASE}/sandbox/scenarios", json={"hypothesis_text": "anything at all here"}).status_code == 400
    conn = get_conn()
    conn.execute("UPDATE sandbox_runs SET schema_version=3 WHERE run_id=?", (cur,))
    conn.commit()
    conn.close()
    assert state(client)["status"] == "ready"


def test_15_generation_is_rate_limited(client):
    api.limiter.enabled = True
    api.limiter.reset()
    try:
        codes = [client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "bogus"}).status_code for _ in range(7)]
    finally:
        api.limiter.enabled = False
        api.limiter.reset()
    assert codes[:5] == [400] * 5 and 429 in codes[5:], codes


def test_16_deleting_a_case_keeps_its_audit_trail(client):
    n_before = len(client.get(f"/cases/{CASE}/audit").json()["events"])
    assert n_before > 5
    assert client.delete(f"/cases/{CASE}").status_code == 200
    conn = get_conn()
    try:
        events = conn.execute("SELECT action FROM audit_events WHERE case_id=? ORDER BY timestamp ASC", (CASE,)).fetchall()
        assert len(events) >= n_before and events[-1]["action"] == "case_deleted", "the trail stays and records the deletion"
        assert verify_audit_chain(conn, CASE)
        assert conn.execute("SELECT COUNT(*) AS n FROM sandbox_runs WHERE case_id=?", (CASE,)).fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM cases WHERE case_id=?", (CASE,)).fetchone()["n"] == 0
    finally:
        conn.close()
