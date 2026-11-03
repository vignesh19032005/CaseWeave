"""Regression tests for the audit fixes: each test names the defect it guards against.

Runs against the throwaway test database (see conftest.py) and, where a queue is involved, a throwaway Redis.
No model is called; model-dependent code is exercised with fakes.
"""
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402
import storage  # noqa: E402
import upload_validation as uv  # noqa: E402
from db import get_conn, append_audit_event, verify_audit_chain, verify_audit_chain_detail  # noqa: E402
from pipeline import timeutil  # noqa: E402


def _uid(prefix="T"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def client():
    return TestClient(api.app)


def _user(role="admin", must_change=False, password="a-long-test-password"):
    name = _uid("u").lower()
    uid = auth.create_user(name, password, role, must_change_password=must_change)
    row = auth.authenticate(name, password)
    return {"user_id": uid, "username": name, "role": role, "password": password, "token": auth.create_token(row)}


def _h(u):
    return {"Authorization": "Bearer " + u["token"]}


@pytest.fixture()
def case(client):
    admin = _user("admin")
    r = client.post("/cases", json={"title": "hardening test"}, headers=_h(admin))
    assert r.status_code == 200, r.text
    cid = r.json()["case_id"]
    yield cid, admin
    client.delete(f"/cases/{cid}", headers=_h(admin))


# ------------------------------------------------------------------ database ----

def test_sql_placeholder_translation_ignores_question_marks_inside_quotes():
    assert db._translate_sql("SELECT * FROM t WHERE a=? AND b='what?' AND c=?") == "SELECT * FROM t WHERE a=%s AND b='what?' AND c=%s"


def test_reset_db_refuses_a_database_that_is_not_a_test_database(monkeypatch):
    monkeypatch.setattr(db, "get_secret", lambda k: "caseweave" if k == "MYSQL_DATABASE" else "")
    monkeypatch.setenv("CASEWEAVE_ALLOW_DB_RESET", "1")
    with pytest.raises(RuntimeError, match="refused"):
        db.reset_db()


def test_reset_db_refuses_without_the_explicit_flag(monkeypatch):
    monkeypatch.delenv("CASEWEAVE_ALLOW_DB_RESET", raising=False)
    with pytest.raises(RuntimeError, match="refused"):
        db.reset_db()


def test_audit_chain_v2_detects_edits_to_any_field_and_deleted_tail(case):
    cid, _ = case
    conn = get_conn()
    for i in range(4):
        append_audit_event(conn, cid, "admin", f"action_{i}", f"target_{i}", actor_user="alice")
    assert verify_audit_chain(conn, cid)
    # editing the role (not covered by the old hash) is now detected
    conn.execute("UPDATE audit_events SET actor_role='reviewer' WHERE case_id=? AND action='action_1'", (cid,))
    conn.commit()
    assert not verify_audit_chain(conn, cid)
    conn.execute("UPDATE audit_events SET actor_role='admin' WHERE case_id=? AND action='action_1'", (cid,))
    conn.commit()
    assert verify_audit_chain(conn, cid)
    # editing the username
    conn.execute("UPDATE audit_events SET actor_user='mallory' WHERE case_id=? AND action='action_2'", (cid,))
    conn.commit()
    assert "altered" in verify_audit_chain_detail(conn, cid)["reason"]
    conn.execute("UPDATE audit_events SET actor_user='alice' WHERE case_id=? AND action='action_2'", (cid,))
    conn.commit()
    # deleting the newest event cannot be hidden by the rest of the chain still linking up
    conn.execute("DELETE FROM audit_events WHERE case_id=? AND action='action_3'", (cid,))
    conn.commit()
    d = verify_audit_chain_detail(conn, cid)
    assert not d["ok"] and "removed" in d["reason"]
    conn.close()


def test_audit_chain_still_verifies_legacy_v1_rows():
    cid = _uid("CW-LEGACY")
    conn = get_conn()
    prev = "GENESIS"
    for i in range(3):
        ts = f"2026-01-01T00:00:0{i}.000000"
        h = db._v1_hash(prev, f"legacy_{i}", "t", ts)
        conn.execute("INSERT INTO audit_events (audit_id, case_id, actor_role, action, target, timestamp, prev_hash, this_hash) VALUES (?,?,?,?,?,?,?,?)",
                     (f"a_{cid}_{i}", cid, "system", f"legacy_{i}", "t", ts, prev, h))
        prev = h
    conn.commit()
    assert verify_audit_chain(conn, cid)
    append_audit_event(conn, cid, "admin", "new_after_legacy", "t", actor_user="bob")   # a v2 event can follow v1 events
    assert verify_audit_chain(conn, cid)
    conn.execute("DELETE FROM audit_events WHERE case_id=?", (cid,))
    conn.execute("DELETE FROM audit_heads WHERE case_id=?", (cid,))
    conn.commit()
    conn.close()


def test_concurrent_audit_appends_do_not_fork_the_chain(case):
    import threading
    cid, _ = case

    def work(n):
        c = get_conn()
        for i in range(5):
            append_audit_event(c, cid, "system", f"t{n}_{i}", "x")
        c.close()

    ts = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    c = get_conn()
    assert verify_audit_chain(c, cid)
    assert c.execute("SELECT COUNT(*) AS n FROM audit_events WHERE case_id=?", (cid,)).fetchone()["n"] >= 20
    c.close()


# ---------------------------------------------------------------------- time ----

@pytest.mark.parametrize("raw,expected", [("9:10 PM", "21:10"), ("02:28:15", "02:28:15"), ("12:05 am", "00:05"), ("around 2:21 AM", "02:21"),
                                          ("25:00", None), ("soon", None), (None, None), ("[+00:12 elapsed]", "00:12")])
def test_normalize_clock(raw, expected):
    assert timeutil.normalize_clock(raw) == expected


def test_midnight_crossing_incident_is_ordered_correctly():
    events = [{"time": t} for t in ("00:10", "23:50", "00:02", "23:58")]
    assert [e["time"] for e in timeutil.sort_chronologically(events)] == ["23:50", "23:58", "00:02", "00:10"]


def test_ordinary_incident_keeps_natural_order_and_untimed_go_last():
    events = [{"time": "02:35"}, {"time": None}, {"time": "01:15"}, {"time": "09:30"}]
    assert [e["time"] for e in timeutil.sort_chronologically(events)] == ["01:15", "02:35", "09:30", None]


# --------------------------------------------------------------- observation ----

def test_observation_cleaning_survives_malformed_model_output():
    from pipeline.observe import clean_observation, split_chunks
    assert clean_observation({"description": None}) is None
    o = clean_observation({"description": " door  opened ", "classification": "MADE UP", "extracted_time": "9:10 PM", "limitations": "single string",
                           "subject": ["not", "text"], "action": 5})
    assert o["description"] == "door opened" and o["classification"] == "unknown" and o["extracted_time"] == "21:10"
    assert o["limitations"] == ["single string"] and o["subject"] is None
    bad_time = clean_observation({"description": "x", "extracted_time": "yesterday evening"})
    assert bad_time["extracted_time"] is None and any("could not be read" in x for x in bad_time["limitations"])
    long = "line one\n" * 3000
    chunks = split_chunks(long, 7000)
    assert len(chunks) > 1 and all(len(c) <= 7000 for c in chunks) and "".join(chunks) == long


# -------------------------------------------------------------------- debate ----

def test_debate_pairs_the_alarm_forced_entry_with_the_cctv_shutter_lift_not_an_unrelated_line():
    from pipeline.discrepancy import _candidate_pairs
    ev = [
        {"event_id": "1", "time": "02:23", "source_evidence_id": "ALARM", "source_observation_id": "o1", "description": "RFID-REAR-01 door_opened at rear_shutter_gate_b, status forced_breach"},
        {"event_id": "2", "time": "02:28", "source_evidence_id": "CCTV", "source_observation_id": "o2", "description": "Male enters camera frame from side alley corner"},
        {"event_id": "3", "time": "02:29", "source_evidence_id": "CCTV", "source_observation_id": "o3", "description": "Individual inserts tool into the bottom lock clasp of the rear shutter and lifts the rolling shutter"},
        {"event_id": "4", "time": "06:30", "source_evidence_id": "STMT", "source_observation_id": "o4", "description": "Upon inspecting the stockroom the cabinet door was found open"},
    ]
    pairs = [(a["event_id"], b["event_id"]) for a, b in _candidate_pairs(ev)]
    assert ("1", "3") in pairs or ("3", "1") in pairs, pairs
    assert not any({"1", "4"} == set(p) for p in pairs), "a claim 4 hours away must not be paired"


def test_event_groups_use_word_boundaries():
    from pipeline.discrepancy import event_groups
    assert "entry" not in event_groups("The entertainment centre was busy")
    assert "entry" in event_groups("The side door was opened")


def test_rerun_keeps_a_reviewers_decision_for_the_same_two_claims(case, monkeypatch):
    import pipeline.discrepancy as d
    cid, _ = case
    events = [
        {"event_id": "e1", "time": "02:23", "source_evidence_id": "A", "source_observation_id": "x1", "classification": "observed", "description": "rear shutter door opened forced"},
        {"event_id": "e2", "time": "02:29", "source_evidence_id": "B", "source_observation_id": "x2", "classification": "observed", "description": "rear shutter door lifted by intruder"},
    ]

    def fake_debate(a, b, ctx, live=False, case_id=None, redactor=None):
        return {"fake"}, {"relationship": "conflicts", "reason": "times differ", "verification_question": "check clock"}, {"claims": "c"}
    monkeypatch.setattr(d, "_debate_adjudicate", fake_debate)
    monkeypatch.setattr(d, "case_redactor", lambda c: None)
    first, _ = d.detect_discrepancies(cid, events)
    assert len(first) == 1
    d.update_review_status(cid, first[0]["conflict_id"], "confirmed", "checked against NVR note", "rev1", "reviewer")
    second, _ = d.detect_discrepancies(cid, events)
    assert second[0]["conflict_id"] != first[0]["conflict_id"] and second[0]["review_status"] == "confirmed"
    c = get_conn()
    assert c.execute("SELECT COUNT(*) AS n FROM conflict_reviews WHERE case_id=? AND status='confirmed'", (cid,)).fetchone()["n"] >= 2
    assert verify_audit_chain(c, cid)
    c.close()


# ------------------------------------------------------------------ entities ----

def test_entity_resolution_never_drops_a_mention_the_model_left_out(case, monkeypatch):
    import pipeline.entities as ent
    cid, _ = case
    conn = get_conn()
    for i, (subj, loc) in enumerate([("R. Kumaran", "rear shutter"), ("Kumaran", "Rear Shutter"), ("CAM-02", "alley")]):
        conn.execute("INSERT INTO observations (observation_id, case_id, description, classification, source_evidence_id, source_locator, extracted_time, limitations, subject, action, location, time_claim) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (f"OBS-H{i}-{cid}", cid, "d", "observed", "EV", "l", None, "[]", subj, "entered", loc, None))
    conn.commit()
    conn.close()
    # the model groups the two Kumaran spellings and forgets CAM-02 and alley entirely
    monkeypatch.setattr(ent, "chat_json", lambda *a, **k: ("meta", [{"canonical_name": "R. Kumaran", "entity_type": "person", "aliases": ["R. Kumaran", "Kumaran"]},
                                                                  {"canonical_name": "rear shutter", "entity_type": "location", "aliases": ["rear shutter"]}]))
    out = ent.resolve_entities(cid)
    names = {e["canonical_name"].lower() for e in out["entities"]}
    assert {"r. kumaran", "rear shutter", "cam-02", "alley"} <= names
    assert len(out["relationships"]) == 3, "relationships for the left-out mentions must not vanish"


# ---------------------------------------------------------------------- auth ----

def test_password_rules_and_72_byte_limit():
    for bad in ("short", "changeme123", "x" * 80):
        with pytest.raises(ValueError):
            auth.validate_new_password(bad)
    assert not auth.verify_password("y" * 100, auth.hash_password("ok-password-123"))   # no crash on over-long input at login


def test_role_comes_from_the_database_not_the_token(client):
    u = _user("investigator")
    assert client.get("/cases", headers=_h(u)).status_code == 200
    c = get_conn()
    c.execute("UPDATE users SET role='reviewer' WHERE user_id=?", (u["user_id"],))
    c.commit()
    c.close()
    r = client.post("/cases", json={"title": "x"}, headers=_h(u))     # token still says investigator; the DB says reviewer
    assert r.status_code == 403
    c = get_conn()
    c.execute("DELETE FROM users WHERE user_id=?", (u["user_id"],))
    c.commit()
    c.close()
    assert client.get("/cases", headers=_h(u)).status_code == 401, "a deleted account loses access at once"


def test_changing_the_password_ends_old_sessions_and_clears_the_forced_change(client):
    u = _user("admin", must_change=True)
    assert client.get("/cases", headers=_h(u)).status_code == 403              # blocked until the password is changed
    assert client.get("/auth/me", headers=_h(u)).status_code == 200
    r = client.post("/auth/change-password", json={"old_password": u["password"], "new_password": "a-brand-new-password"}, headers=_h(u))
    assert r.status_code == 200 and r.json()["must_change_password"] is False
    assert client.get("/cases", headers=_h(u)).status_code == 401               # the old token is dead
    assert client.get("/cases", headers={"Authorization": "Bearer " + r.json()["access_token"]}).status_code == 200
    assert client.post("/auth/change-password", json={"old_password": "wrong", "new_password": "another-long-password"}, headers={"Authorization": "Bearer " + r.json()["access_token"]}).status_code == 400


def test_default_password_accounts_are_flagged_at_startup():
    name = _uid("def").lower()
    auth.create_user(name, auth.DEFAULT_ADMIN_PASSWORD, "investigator", enforce_policy=False)
    assert auth.flag_default_passwords() >= 1
    c = get_conn()
    assert c.execute("SELECT must_change_password FROM users WHERE username=?", (name,)).fetchone()["must_change_password"] == 1
    c.execute("DELETE FROM users WHERE username=?", (name,))
    c.commit()
    c.close()


def test_login_response_time_does_not_reveal_whether_the_username_exists():
    import time
    u = _user("investigator")
    def t(name):
        s = time.perf_counter()
        with pytest.raises(ValueError):
            auth.authenticate(name, "wrong-password-xyz")
        return time.perf_counter() - s
    known, unknown = min(t(u["username"]) for _ in range(3)), min(t("nobody-" + _uid()) for _ in range(3))
    assert unknown > 0.5 * known, (known, unknown)    # both run a full bcrypt check


def test_user_management_is_admin_only_and_protects_the_last_admin(client):
    inv, adm = _user("investigator"), _user("admin")
    assert client.get("/auth/users", headers=_h(inv)).status_code == 403
    assert client.get("/auth/users", headers=_h(adm)).status_code == 200
    r = client.post("/auth/register", json={"username": _uid("n").lower(), "password": "x"}, headers=_h(adm))
    assert r.status_code == 422 or r.status_code == 400
    assert client.delete(f"/auth/users/{adm['user_id']}", headers=_h(adm)).status_code == 400, "you cannot delete yourself"


# ------------------------------------------------------------- authorization ----

def test_every_case_endpoint_needs_a_token_and_the_right_role(client, case):
    cid, admin = case
    anon = [("get", f"/cases/{cid}"), ("get", f"/cases/{cid}/timeline"), ("get", f"/cases/{cid}/audit"), ("get", f"/cases/{cid}/conflicts"),
            ("get", f"/cases/{cid}/entities"), ("post", f"/cases/{cid}/chat"), ("post", f"/cases/{cid}/reconstruct"), ("get", f"/cases/{cid}/patterns"),
            ("get", f"/cases/{cid}/legal-advisory"), ("get", "/legal/sections"), ("post", "/cases/patterns/seed"), ("get", f"/cases/{cid}/process/status/x")]
    for method, path in anon:
        assert getattr(client, method)(path).status_code == 401, (method, path)
    reviewer = _user("reviewer")
    for method, path in (("post", f"/cases/{cid}/reconstruct"), ("post", "/cases/patterns/seed"), ("post", f"/cases/{cid}/entities/resolve"),
                         ("post", f"/cases/{cid}/patterns/extract")):
        assert getattr(client, method)(path, headers=_h(reviewer)).status_code == 403, (method, path)


def test_unknown_case_is_404_everywhere_not_an_empty_success(client):
    admin = _user("admin")
    for path in ("timeline", "audit", "conflicts", "entities", "evidence", "evidence-links", "patterns", "legal-compliance", "legal-advisory", "report", "narrative"):
        assert client.get(f"/cases/CW-NOPE00/{path}", headers=_h(admin)).status_code == 404, path


def test_job_status_of_another_case_is_not_revealed(client, case):
    from job_queue import get_queue, get_redis_connection
    cid, admin = case
    other = client.post("/cases", json={"title": "other"}, headers=_h(admin)).json()["case_id"]
    try:
        job = get_queue().enqueue("job_queue.run_process_job", other, None, meta={"case_id": other}, job_timeout=60)
        r = client.get(f"/cases/{cid}/process/status/{job.id}", headers=_h(admin))
        assert r.json() == {"status": "not_found"}
        assert client.get(f"/cases/{other}/process/status/{job.id}", headers=_h(admin)).json()["status"] in ("queued", "started", "finished", "failed")
        job.delete()
    finally:
        client.delete(f"/cases/{other}", headers=_h(admin))
        get_redis_connection().delete(f"cw:case-job:{other}")


# -------------------------------------------------------------- uploads/files ----

def test_upload_rules_unknown_type_spoofed_binary_bad_json_duplicates_and_names(client, case):
    cid, admin = case
    H = _h(admin)
    up = lambda name, data: client.post(f"/cases/{cid}/evidence", files={"file": (name, data)}, headers=H)
    assert up("tool.exe", b"MZ....").status_code == 400                         # unsupported type is refused, not stored and skipped
    assert up("fake.pdf", b"not a pdf").status_code == 400
    assert up("bin.txt", b"hello\x00world").status_code == 400                  # binary inside a "text" file
    assert up("bad.json", b"{not json").status_code == 400
    assert up("empty.txt", b"").status_code == 400
    ok = up("../../a:b*c?.txt", "witness says 02:21 கு".encode("utf-8"))
    assert ok.status_code == 200 and "/" not in ok.json()["filename"] and ":" not in ok.json()["filename"], ok.text
    dup = up("same-content-other-name.txt", "witness says 02:21 கு".encode("utf-8"))
    assert dup.status_code == 409 and ok.json()["evidence_id"] in dup.json()["detail"]
    ev = client.get(f"/cases/{cid}/evidence", headers=H).json()
    assert len(ev) == 1


def test_tampered_stored_file_is_refused_audited_and_flagged_on_the_certificate(client, case):
    cid, admin = case
    H = _h(admin)
    r = client.post(f"/cases/{cid}/evidence", files={"file": ("note.txt", b"original statement text")}, headers=H).json()
    eid = r["evidence_id"]
    assert client.get(f"/cases/{cid}/evidence/{eid}/file", headers=H).content == b"original statement text"
    path = storage.get_object_path(cid, eid, "note.txt")
    assert not os.access(path, os.W_OK), "stored originals are read-only"
    os.chmod(path, 0o600)
    path.write_bytes(b"altered statement text!")
    bad = client.get(f"/cases/{cid}/evidence/{eid}/file", headers=H)
    assert bad.status_code == 409 and "hash" in bad.json()["detail"]
    cert = client.get(f"/cases/{cid}/evidence/{eid}/certificate", headers=H)
    assert cert.status_code == 200 and cert.content.startswith(b"%PDF")
    c = get_conn()
    assert c.execute("SELECT COUNT(*) AS n FROM audit_events WHERE case_id=? AND action='evidence_integrity_failure'", (cid,)).fetchone()["n"] >= 1
    c.close()


def test_extraction_child_process_gets_no_secrets(monkeypatch):
    monkeypatch.setenv("MYSQL_PASSWORD", "super-secret-db")
    monkeypatch.setenv("JWT_SECRET", "super-secret-jwt")
    monkeypatch.setenv("GROQ_API_KEY", "super-secret-key")
    env = uv._child_env()
    assert not any("secret" in v for v in env.values()) and "PATH" in env


def test_storage_rejects_paths_that_climb_out_of_the_store():
    for bad in ("..", "a/b", "a\\b", ""):
        with pytest.raises(ValueError):
            storage._safe_part(bad)


# ------------------------------------------------------- deletion and reports ----

def test_delete_case_removes_signatures_and_files_and_keeps_a_verifiable_audit(client):
    admin = _user("admin")
    H = _h(admin)
    cid = client.post("/cases", json={"title": "to delete"}, headers=H).json()["case_id"]
    eid = client.post(f"/cases/{cid}/evidence", files={"file": ("n.txt", b"delete me")}, headers=H).json()["evidence_id"]
    c = get_conn()
    c.execute("REPLACE INTO case_signatures (case_id, crime_category) VALUES (?, 'x')", (cid,))
    c.commit()
    c.close()
    assert client.delete(f"/cases/{cid}", headers=H).status_code == 200
    c = get_conn()
    assert not c.execute("SELECT 1 FROM case_signatures WHERE case_id=?", (cid,)).fetchone()
    assert not c.execute("SELECT 1 FROM cases WHERE case_id=?", (cid,)).fetchone()
    ev = c.execute("SELECT actor_user, action FROM audit_events WHERE case_id=? ORDER BY timestamp DESC LIMIT 1", (cid,)).fetchone()
    assert ev["action"] == "case_deleted" and ev["actor_user"] == admin["username"]
    assert verify_audit_chain(c, cid)
    c.close()
    assert not (storage.STORE_ROOT / cid).exists()


def test_reference_cases_are_labelled_synthetic_and_never_listed_as_real_cases(client):
    from pipeline import patterns
    patterns.seed_historical_patterns()
    admin = _user("admin")
    listed = [c["case_id"] for c in client.get("/cases", headers=_h(admin)).json()]
    assert not any(i.startswith("CW-HIST-") for i in listed)
    assert all("demo reference" in c["fir_number"] for c in patterns.HISTORICAL_SEED_CASES)


def test_pattern_intelligence_never_invents_a_signature_when_the_model_is_down(case, monkeypatch):
    from pipeline import patterns
    from llm_client import LLMUnavailableError
    cid, _ = case
    conn = get_conn()
    conn.execute("INSERT INTO observations (observation_id, case_id, description, classification, source_evidence_id, source_locator, extracted_time, limitations, subject, action, location, time_claim) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (f"OBS-P-{cid}", cid, "a window was found open", "observed", "EV", "l", None, "[]", None, None, None, None))
    conn.commit()
    conn.close()

    def down(*a, **k):
        raise LLMUnavailableError("down")
    monkeypatch.setattr(patterns, "safe_chat_json", down)
    out = patterns.get_case_patterns(cid, force=True)
    assert out["status"] == "unavailable" and out["active_signature"] is None and out["similar_cases"] == []
    c = get_conn()
    assert not c.execute("SELECT 1 FROM case_signatures WHERE case_id=?", (cid,)).fetchone(), "nothing was stored"
    c.close()


def test_legal_advisory_assumes_nothing_when_the_model_is_down_and_does_not_claim_compliance(case, monkeypatch):
    from pipeline import legal_advisor as la
    from llm_client import LLMUnavailableError
    cid, _ = case
    conn = get_conn()
    conn.execute("INSERT INTO evidence_items (evidence_id, case_id, filename, file_hash, evidence_type, status) VALUES (?,?,?,?,?,?)", (f"EV-{cid}-1", cid, "a.jpg", "h", "image", "uploaded"))
    conn.execute("INSERT INTO observations (observation_id, case_id, description, classification, source_evidence_id, source_locator, extracted_time, limitations, subject, action, location, time_claim) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (f"OBS-L-{cid}", cid, "a shutter was found raised", "observed", "EV", "l", None, "[]", None, None, None, None))
    conn.commit()
    conn.close()

    def down(*a, **k):
        raise LLMUnavailableError("down")
    monkeypatch.setattr(la, "safe_chat_json", down)
    out = la.get_fir_legal_advisory(cid)
    assert out["status"] == "unavailable" and out["advisory"]["recommended_sections"] == []
    assert "hooded" not in json.dumps(out) and "nitrile" not in json.dumps(out)
    by_rule = {i["rule"]: i for i in out["compliance_audit"]["compliance_items"]}
    assert by_rule["BNSS Section 105 audio-video recording of search and seizure"]["status"] == "NOT_VERIFIED"
    assert by_rule["Accused's age"]["status"] == "AGE_NOT_ESTABLISHED"
    assert by_rule["BSA Section 63 electronic evidence certificate"]["status"] == "CERTIFICATE_REQUIRED"   # an image is an electronic record


def test_report_shows_the_reviewers_decision_after_it_is_made(client, case):
    cid, admin = case
    conn = get_conn()
    conn.execute("INSERT INTO conflicts (conflict_id, case_id, claim_a, source_a, time_a, claim_b, source_b, time_b, question, nature_of_conflict, transcript, review_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (f"CFL-{cid}", cid, "alarm 02:23", "EV-A", "02:23", "cctv 02:28", "EV-B", "02:28", "check NVR clock", "6 minutes apart", "{}", "unresolved"))
    conn.commit()
    conn.close()
    from pipeline.report_refresh import refresh_reports
    refresh_reports(cid)                                                    # the report exists, with the conflict unresolved
    assert "Review status: **unresolved**" in client.get(f"/cases/{cid}/report", headers=_h(admin)).text
    r = client.patch(f"/cases/{cid}/conflicts/CFL-{cid}/review", json={"status": "confirmed", "reason": "NVR clock offset verified"}, headers=_h(admin))
    assert r.status_code == 200
    text = client.get(f"/cases/{cid}/report", headers=_h(admin)).text
    assert "Review status: **confirmed**" in text and "NVR clock offset verified" in text
    pdf = client.get(f"/cases/{cid}/report/pdf", headers=_h(admin))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_pdfs_can_draw_tamil_text():
    from pipeline import pdf_fonts
    from pipeline.report_pdf import esc, _p
    from reportlab.platypus import SimpleDocTemplate
    import io
    text = "சாட்சி அறிக்கை: 02:21 மணிக்கு சத்தம் கேட்டது"
    if not pdf_fonts.UNICODE:
        pytest.skip("no Unicode font on this machine; text falls back to '?' instead of boxes")
    buf = io.BytesIO()
    SimpleDocTemplate(buf).build([_p(esc(text))])
    data = buf.getvalue()
    assert data.startswith(b"%PDF") and b"/FontFile2" in data, "an embedded TrueType font is used"
    import fitz
    page_text = fitz.open(stream=data, filetype="pdf")[0].get_text()
    assert "சாட்சி" in page_text and "02:21" in page_text, "the Tamil text is really in the PDF, not boxes"


# ---------------------------------------------------------------- job queue ----

def test_jobs_are_json_serialised_and_a_case_cannot_be_processed_twice_at_once():
    import job_queue as jq
    from rq.serializers import JSONSerializer
    assert jq.get_queue().serializer is JSONSerializer
    cid = _uid("CW-Q")
    try:
        job_id = jq.enqueue_process(cid, None)
        with pytest.raises(jq.CaseBusy):
            jq.enqueue_process(cid, None)
        assert jq.active_job_for_case(cid) == job_id
        from rq.job import Job
        job = Job.fetch(job_id, connection=jq.get_redis_connection(), serializer=JSONSerializer)
        assert b"pickle" not in (job.data or b"") and job.meta["case_id"] == cid
        job.delete()
    finally:
        jq.release_case(cid)
    jq.enqueue_process(cid, None)
    jq.release_case(cid)


# ------------------------------------------------------------------- backup ----

def test_a_failed_backup_never_replaces_the_last_good_one(tmp_path, monkeypatch):
    import backup
    monkeypatch.setenv("CASEWEAVE_BACKUP_DIR", str(tmp_path / "CW_Backup"))
    good = tmp_path / "CW_Backup"
    good.mkdir()
    (good / "caseweave.sql").write_text("PRECIOUS", encoding="utf-8")
    monkeypatch.setattr(backup, "_find_mysqldump", lambda: None)
    result = backup.run_backup()
    assert result["errors"] and "mysqldump" in result["errors"][0]
    assert (good / "caseweave.sql").read_text(encoding="utf-8") == "PRECIOUS"
    assert (tmp_path / "CW_Backup.failed").exists()


def test_backup_password_is_not_on_the_command_line(tmp_path, monkeypatch):
    import backup, subprocess
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["env"] = cmd, kw.get("env", {})
        open(tmp_path / "caseweave.sql", "a").write("-- dump")
        class R: returncode = 0; stderr = ""
        return R()
    monkeypatch.setattr(backup, "_find_mysqldump", lambda: "mysqldump")
    monkeypatch.setattr(backup.subprocess, "run", fake_run)
    monkeypatch.setattr(backup, "get_secret", lambda k: {"MYSQL_PASSWORD": "pw-xyz"}.get(k, ""))
    ok, err = backup._backup_mysql(tmp_path)
    assert ok and not any("pw-xyz" in part for part in seen["cmd"]) and seen["env"]["MYSQL_PWD"] == "pw-xyz"


def test_encrypted_backup_round_trips_and_leaves_nothing_readable(tmp_path, monkeypatch):
    import backup, tarfile
    monkeypatch.setenv("CASEWEAVE_BACKUP_DIR", str(tmp_path / "CW_Backup"))
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", "a long test passphrase")
    monkeypatch.setattr(backup, "BACKEND_DIR", tmp_path / "be")
    (tmp_path / "be" / "object_store" / "CW-X").mkdir(parents=True)
    (tmp_path / "be" / "object_store" / "CW-X" / "secret.txt").write_text("witness statement SECRET-MARKER", encoding="utf-8")

    def fake_dump(dest):
        (dest / "caseweave.sql").write_text("-- SQL-SECRET-MARKER", encoding="utf-8")
        return True, ""
    monkeypatch.setattr(backup, "_backup_mysql", fake_dump)
    result = backup.run_backup()
    assert not result["errors"], result
    out = tmp_path / "CW_Backup"
    assert sorted(p.name for p in out.iterdir()) == ["caseweave_backup.tar.gz.enc", "last_backup.txt"]
    blob = (out / "caseweave_backup.tar.gz.enc").read_bytes()
    assert b"SECRET-MARKER" not in blob and blob.startswith(backup.MAGIC)
    with pytest.raises(ValueError, match="wrong passphrase"):
        backup.decrypt_file(out / "caseweave_backup.tar.gz.enc", tmp_path / "bad.tar.gz", "not the passphrase")
    backup.decrypt_file(out / "caseweave_backup.tar.gz.enc", tmp_path / "ok.tar.gz", "a long test passphrase")
    with tarfile.open(tmp_path / "ok.tar.gz") as t:
        names = t.getnames()
        assert "caseweave.sql" in names and any(n.endswith("secret.txt") for n in names)


def test_location_mentions_are_merged_only_when_clearly_contained():
    from pipeline.entities import _merge_contained_locations
    by_key = {
        "rear shutter": {"texts": {"rear shutter"}, "type": "location"},
        "rear shutter gate b": {"texts": {"rear_shutter_gate_b"}, "type": "location"},
        "shutter": {"texts": {"shutter"}, "type": "location"},                  # one word: never merged
        "side door": {"texts": {"side door"}, "type": "location"},
        "side door east": {"texts": {"side door east"}, "type": "location"},
        "side door west": {"texts": {"side door west"}, "type": "location"},    # "side door" fits two places: ambiguous, left alone
        "kumaran": {"texts": {"Kumaran"}, "type": "person_or_device"},
    }
    _merge_contained_locations(by_key)
    assert "rear shutter" not in by_key and by_key["rear shutter gate b"]["texts"] == {"rear shutter", "rear_shutter_gate_b"}
    assert {"shutter", "side door", "side door east", "side door west", "kumaran"} <= set(by_key)


def test_layout_similarity_matches_by_name_not_by_model_chosen_id():
    from pipeline import sandbox_geometry as geo
    def lay(room_id, door_id):
        return {"rooms": [{"id": room_id, "label": "Shop Floor", "width_m": 8, "length_m": 6}],
                "openings": [{"id": door_id, "label": "Rear shutter", "state": "forced"}], "fixtures": [{"id": room_id + "_c", "label": "Counter"}]}
    s = geo.layout_similarity(lay("shop", "rear"), lay("shop_floor", "rear_shutter_gate"))
    assert s["score"] >= 0.95, s     # the same room and door under different ids are the same
