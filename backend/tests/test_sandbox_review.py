"""The reviewer model: what it is shown, how its answers are checked, and the API around it. The model is faked."""
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from test_sandbox_api import CASE, ROLE, FakeModel, client, state  # noqa: E402,F401
from pipeline import sandbox_review, sandbox_reviewer as rv  # noqa: E402


# ---------------------------------------------------------------- checking what the reviewer says

FRAMES = {"F1", "F2", "F3"}
REFS = {"OBS-T1", "OBS-T2"}


def test_a_finding_that_points_at_nothing_real_is_dropped():
    raw = {"findings": [
        {"severity": "problem", "type": "role", "step": 2, "frames": ["F2"], "evidence_refs": ["OBS-T1"], "text": "The owner takes cash although the evidence calls them the owner."},
        {"severity": "problem", "type": "spatial", "step": 99, "frames": ["F99"], "evidence_refs": ["OBS-NOPE"], "text": "This cites a picture and evidence that do not exist."},
        {"severity": "concern", "type": "other", "text": "A vague feeling with no step, picture or evidence behind it."},
    ]}
    kept, dropped = rv.verify_findings(raw, FRAMES, REFS, max_step=5)
    assert len(kept) == 1 and kept[0]["step"] == 2 and dropped == 2


def test_invalid_citations_are_stripped_but_a_valid_one_keeps_the_finding():
    raw = {"findings": [{"severity": "concern", "type": "evidence_mismatch", "step": None, "frames": ["F1", "F77"], "evidence_refs": ["OBS-T2", "OBS-XX"],
                         "text": "The cited statement says the door was locked, the scenario says open."}]}
    kept, _ = rv.verify_findings(raw, FRAMES, REFS, 3)
    assert kept[0]["frames"] == ["F1"] and kept[0]["evidence_refs"] == ["OBS-T2"] and kept[0]["removed_citations"] == 2


def test_unknown_types_and_severities_are_normalised_and_duplicates_merged_and_the_list_capped():
    raw = {"findings": [{"severity": "catastrophic", "type": "made_up", "step": 1, "text": "Something is off about step one for sure."}] * 3 +
           [{"severity": "note", "type": "role", "step": 1, "text": f"Distinct observation number {i} about the roles."} for i in range(20)]}
    kept, dropped = rv.verify_findings(raw, FRAMES, REFS, 5)
    assert len(kept) == rv.MAX_FINDINGS and kept[0]["severity"] == "concern" and kept[0]["type"] == "other"
    assert sum(1 for k in kept if k["text"].startswith("Something is off")) == 1


def test_too_short_or_malformed_findings_are_dropped_and_non_lists_are_safe():
    assert rv.verify_findings({"findings": "nope"}, FRAMES, REFS, 3) == ([], 0)
    kept, dropped = rv.verify_findings({"findings": [{"text": "x", "step": 1}, "string", None]}, FRAMES, REFS, 3)
    assert kept == [] and dropped == 3


def test_the_verdict_is_honest_about_what_nothing_found_means():
    assert rv.verdict([]) == "nothing_found"
    assert rv.verdict([{"severity": "note"}]) == "notes_only"
    assert rv.verdict([{"severity": "concern"}, {"severity": "note"}]) == "concerns"
    assert rv.verdict([{"severity": "problem"}]) == "problems"


# ---------------------------------------------------------------- through the API with a fake reviewer

SEEN = []


def fake_reviewer(system, text, images):
    SEEN.append({"system": system[:40], "text": text, "images": len(images)})
    return {"provider": "fake", "model": "fake-vision", "parsed": {"findings": [
        {"severity": "concern", "type": "spatial", "step": 1, "frames": ["F1"], "evidence_refs": ["OBS-T2"], "text": "The scene at the start shows the rear shutter closed although the evidence says it was forced.", "suggested_fix": "Show it forced."},
        {"severity": "problem", "type": "role", "text": "A finding that points at nothing the reader can check at all."}]}}


@pytest.fixture()
def reviewer(monkeypatch):
    SEEN.clear()
    monkeypatch.setattr(sandbox_review, "make_call", lambda redactor: fake_reviewer)
    ROLE["v"] = "admin"
    yield
    ROLE["v"] = "admin"


def _generate(client):
    assert client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "full"}).status_code == 202
    assert state(client)["status"] == "ready"


def test_a_review_runs_in_the_background_and_every_scenario_gets_one(client, reviewer):
    _generate(client)
    assert client.get(f"/cases/{CASE}/sandbox/review").json()["status"] == "none"
    r = client.post(f"/cases/{CASE}/sandbox/review")
    assert r.status_code == 202 and r.json()["status"] == "running"
    got = client.get(f"/cases/{CASE}/sandbox/review").json()
    assert got["status"] == "done" and got["stale"] is False
    scens = got["content"]["scenarios"]
    assert len(scens) == len(state(client)["scenarios"]) and all(s["batches"] >= 1 for s in scens)
    for s in scens:
        assert len(s["findings"]) == 1 and s["findings"][0]["frames"] == ["F1"] and s["dropped_findings"] >= 1
        assert s["verdict"] == "concerns" and "opinion" in s["note"]
        assert s["frames"][0]["kind"] == "start" and s["frames"][-1]["kind"] == "overview"


def test_the_reviewer_is_given_the_scenario_the_evidence_and_the_frames(client, reviewer):
    _generate(client)
    client.post(f"/cases/{CASE}/sandbox/review")
    text = SEEN[0]["text"]
    assert "STEPS (person" in text and "THE EVIDENCE TEXT THE SCENARIO CITES" in text and "PLAN-VIEW FRAMES IN THIS BATCH" in text and "F1 [start]" in text
    assert SEEN[0]["images"] >= 1 and "<case_data>" in text


def test_names_never_reach_the_reviewer_when_redaction_is_on(client, reviewer):
    _generate(client)
    client.post(f"/cases/{CASE}/sandbox/review")
    assert not any("Ramesh Kumaran" in s["text"] for s in SEEN)


def test_the_pictures_it_saw_can_be_fetched_but_only_by_exact_name(client, reviewer):
    _generate(client)
    client.post(f"/cases/{CASE}/sandbox/review")
    got = client.get(f"/cases/{CASE}/sandbox/review").json()
    s = got["content"]["scenarios"][0]
    png = client.get(f"/cases/{CASE}/sandbox/review/{got['review_id']}/frames/{s['frame_files']['F1']}")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png" and png.content[:4] == b"\x89PNG"
    for bad in ("..%2F..%2Fapi.py", "F1.png", "x_F1.png.exe", "a/../b_F1.png"):
        assert client.get(f"/cases/{CASE}/sandbox/review/{got['review_id']}/frames/{bad}").status_code in (404, 422)
    assert client.get(f"/cases/NO-SUCH/sandbox/review/{got['review_id']}/frames/{s['frame_files']['F1']}").status_code == 404


def test_only_investigators_and_admins_can_start_a_review_but_anyone_with_access_can_read_it(client, reviewer):
    _generate(client)
    ROLE["v"] = "reviewer"
    assert client.post(f"/cases/{CASE}/sandbox/review").status_code == 403
    assert client.get(f"/cases/{CASE}/sandbox/review").status_code == 200


def test_a_review_goes_stale_when_the_scene_is_rebuilt_and_the_audit_trail_records_it(client, reviewer):
    _generate(client)
    client.post(f"/cases/{CASE}/sandbox/review")
    client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "full"})
    assert client.get(f"/cases/{CASE}/sandbox/review").json()["stale"] is True
    actions = [e["action"] for e in client.get(f"/cases/{CASE}/audit").json()["events"]]
    assert "sandbox_review_started" in actions and "sandbox_review_completed" in actions


def test_a_failing_reviewer_model_records_a_failed_review_not_a_crash(client, monkeypatch):
    def boom(system, text, images):
        raise RuntimeError("model down")

    monkeypatch.setattr(sandbox_review, "make_call", lambda redactor: boom)
    ROLE["v"] = "admin"
    _generate(client)
    client.post(f"/cases/{CASE}/sandbox/review")
    got = client.get(f"/cases/{CASE}/sandbox/review").json()
    assert got["status"] == "done"          # the run itself finishes: every batch failed, so each scenario says it was not reviewed
    assert all(s["verdict"] == "not_reviewed" and s["batches_failed"] == s["batches"] for s in got["content"]["scenarios"])
