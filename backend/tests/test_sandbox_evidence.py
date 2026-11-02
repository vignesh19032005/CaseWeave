"""Tests for the evidence layer: what the model sees, citation checks, clock
parsing and anchoring (any number of people), stale-evidence diffs and scoring."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import sandbox_evidence as evd  # noqa: E402


def fake_ev():
    return {
        "evidence_items": [{"evidence_id": "EV-1", "filename": "cctv.mp4", "evidence_type": "video", "file_hash": "h1"}],
        "observations": [
            {"observation_id": "OBS-a", "description": "Rear shutter lifted from the alley", "extracted_time": "01:15", "classification": "observed", "source_evidence_id": "EV-1", "source_locator": "00:00:10", "time_claim": None},
            {"observation_id": "OBS-b", "description": "Person at the front counter taking cash", "extracted_time": "01:19", "classification": "observed", "source_evidence_id": "EV-1", "source_locator": "", "time_claim": None},
            {"observation_id": "OBS-c", "description": "Witness says nothing about timing", "extracted_time": None, "classification": "reported", "source_evidence_id": "EV-1", "source_locator": "", "time_claim": None},
        ],
        "entities": [{"entity_id": "ENT-1", "canonical_name": "Pharmacy", "entity_type": "location"}],
        "conflicts": [{"conflict_id": "C-1", "claim_a": "a", "claim_b": "b", "review_status": "resolved", "source_a": "EV-1", "time_a": "01:15", "source_b": "EV-1", "time_b": "01:19", "nature_of_conflict": "x"}],
        "relationships": [], "timeline": [],
    }


def actor(aid, steps, label=None):
    return {"id": aid, "label": label or aid, "steps": steps}


def step(k, t, refs, label="spot"):
    return {"k": k, "arrive_s": t, "label": label, "evidence_refs": refs}


# ---------------------------------------------------------------- what the model sees

def test_known_refs_include_untimed_observations_and_evidence_ids():
    assert {"OBS-a", "OBS-c", "ENT-1", "EV-1"} <= evd.known_refs(fake_ev())


def test_context_wraps_evidence_labels_status_and_includes_untimed():
    text, stats = evd.evidence_context(fake_ev())
    assert text.startswith("<evidence_data>") and text.rstrip().endswith("</evidence_data>")
    assert "[OBS-c] untimed" in text and "[resolved]" in text and stats["observations_omitted"] == 0


def test_oversized_cases_keep_the_scene_relevant_observations_and_disclose_the_rest():
    ev = fake_ev()
    junk = [{"observation_id": f"OBS-j{i}", "description": f"Weather note number {i} about nothing special", "extracted_time": None, "classification": "reported",
             "source_evidence_id": "EV-1", "source_locator": "", "time_claim": None} for i in range(evd.MAX_PROMPT_OBSERVATIONS + 40)]
    ev["observations"] = ev["observations"] + junk
    text, stats = evd.evidence_context(ev)
    assert "[OBS-a]" in text and "[OBS-b]" in text, "door/counter observations outrank filler"
    assert stats["observations_omitted"] == len(ev["observations"]) - evd.MAX_PROMPT_OBSERVATIONS and "were not included" in text


# ---------------------------------------------------------------- stale evidence

def test_fingerprint_changes_and_diff_explains_it():
    a, b = fake_ev(), fake_ev()
    assert evd.evidence_fingerprint(a) == evd.evidence_fingerprint(b)
    old = evd.fingerprint_parts(a)
    b["observations"][0]["description"] = "Rear shutter was NOT lifted"
    b["observations"].append({**b["observations"][1], "observation_id": "OBS-new"})
    b["conflicts"][0]["review_status"] = "unresolved"
    assert evd.evidence_fingerprint(a) != evd.evidence_fingerprint(b)
    diff = evd.diff_parts(old, evd.fingerprint_parts(b))
    assert diff["any"] and diff["observations"] == {"added": 1, "removed": 0, "changed": 1} and diff["conflicts"]["changed"] == 1
    text = evd.describe_diff(diff)
    assert "1 observation added" in text and "1 observation changed" in text


# ---------------------------------------------------------------- clock parsing

def test_parse_clock_variants():
    assert evd.parse_clock("01:15")["sod"] == 4500
    assert evd.parse_clock("01:15:30")["sod"] == 4530
    assert evd.parse_clock(None, "around 9:10 PM, maybe a few minutes before")["sod"] == 21 * 3600 + 10 * 60
    assert evd.parse_clock("", "11 pm")["sod"] == 23 * 3600
    assert evd.parse_clock("12:05 am")["sod"] == 5 * 60
    assert evd.parse_clock("25:99") is None and evd.parse_clock("later") is None and evd.parse_clock(None) is None
    d1 = evd.parse_clock("02:00", "on 2026-03-05")
    d2 = evd.parse_clock("02:00", "on 06/03/2026")
    d3 = evd.parse_clock("02:00", "on 7 March 2026")
    assert d1["day"] is not None and d2["day"] - d1["day"] == 1 and d3["day"] - d2["day"] == 1
    assert evd.parse_clock("02:00")["day"] is None


def test_clock_mentions_in_free_text():
    assert evd.clock_mentions("He left at 23:40 and returned around 1:05 am") == [23 * 3600 + 40 * 60, 3900]
    assert evd.clock_mentions("a 3.5 m door and room 204") == []


# ---------------------------------------------------------------- anchors (any number of people)

def test_anchor_time_conflict_detected_within_one_person():
    ev = fake_ev()
    res = evd.compute_time_anchors([actor("a", [step(0, 0, ["OBS-a"]), step(1, 600, ["OBS-b"])])], ev)
    assert res["basis"] == "anchored" and any(v["code"] == "anchor_time_conflict" for v in res["violations"])


def test_anchor_consistent_unmodelled_gap_and_order():
    ev = fake_ev()
    ok = evd.compute_time_anchors([actor("a", [step(0, 0, ["OBS-a"]), step(1, 30, ["OBS-b"])])], ev)
    assert ok["violations"] == [] and ok["unmodelled_gaps"][0]["unmodelled_s"] > 200
    bad = evd.compute_time_anchors([actor("a", [step(0, 0, ["OBS-b"]), step(1, 20, ["OBS-a"])])], ev)
    assert any(v["code"] == "anchor_order_conflict" for v in bad["violations"])


def test_each_person_is_checked_separately_and_shares_one_clock():
    ev = fake_ev()
    res = evd.compute_time_anchors([actor("a", [step(0, 0, ["OBS-a"]), step(1, 400, ["OBS-b"])], "Ann"),
                                    actor("b", [step(0, 100, ["OBS-a"]), step(1, 130, ["OBS-b"])], "Ben")], ev)
    msgs = [v["message"] for v in res["violations"]]
    assert any("Ann" in m for m in msgs) and not any("Ben" in m for m in msgs), "only the person whose own times conflict is flagged"
    assert len(res["clock_anchors"]) == 4 and res["clock_anchors"] == sorted(res["clock_anchors"], key=lambda x: x["t_model"])
    assert res["cross_person_notes"], "people implying different clock origins must be flagged"


def test_disagreement_between_different_recordings_is_a_caution_not_a_failure():
    ev = fake_ev()
    ev["evidence_items"].append({"evidence_id": "EV-2", "filename": "alarm.log", "evidence_type": "log", "file_hash": "h2"})
    ev["observations"][1]["source_evidence_id"] = "EV-2"
    res = evd.compute_time_anchors([actor("a", [step(0, 0, ["OBS-a"]), step(1, 600, ["OBS-b"])])], ev)
    assert res["violations"] == [] and res["cross_source_notes"] and "alarm.log" in res["cross_source_notes"][0]


def test_dates_make_day_apart_events_consistent():
    ev = fake_ev()
    ev["observations"][0].update({"extracted_time": "23:50", "time_claim": "2026-03-05 23:50"})
    ev["observations"][1].update({"extracted_time": "00:10", "time_claim": "2026-03-06 00:10"})
    res = evd.compute_time_anchors([actor("a", [step(0, 0, ["OBS-a"]), step(1, 900, ["OBS-b"])])], ev)
    assert res["violations"] == [], "20 minutes apart across midnight, with dates, is fine"


def test_no_anchor_means_no_clock_and_officer_time_fills_in_only_when_stated():
    ev = fake_ev()
    res = evd.compute_time_anchors([actor("a", [step(0, 0, ["OBS-c"])])], ev)
    assert res["basis"] == "none" and res["anchors"] == []
    res2 = evd.compute_time_anchors([actor("a", [step(0, 0, ["OBS-c"])])], ev, officer_times=[23 * 3600 + 45 * 60])
    assert res2["basis"] == "officer" and res2["clock_anchors"][0]["sod"] == 23 * 3600 + 45 * 60 and "officer" in res2["note"]
    res3 = evd.compute_time_anchors([actor("a", [step(0, 0, ["OBS-a"])])], ev, officer_times=[14 * 3600])
    assert res3["basis"] == "anchored" and res3["officer_differs"] == 1


# ---------------------------------------------------------------- citation checks

def test_fake_citations_are_stripped_and_reported():
    known = evd.known_refs(fake_ev())
    assert evd.clean_refs(["OBS-a", "OBS-zzz", "[ENT-1]", "OBS-a"], known) == (["OBS-a", "ENT-1"], ["OBS-zzz"])


def test_bracketed_citations_in_text_are_verified():
    known = evd.known_refs(fake_ev())
    facts = evd.clean_facts(["Shutter lifted [OBS-a] and a made-up fact [OBS-fake]", "No citation here"], known)
    assert facts[0]["refs"] == ["OBS-a"] and facts[0]["invalid_refs"] == ["OBS-fake"] and facts[0]["supported"] and not facts[1]["supported"]


def test_citation_relevance_flags_citations_that_do_not_concern_the_claim():
    ev = fake_ev()
    idx = evd.build_evidence_index(ev, {"OBS-a", "OBS-b"})
    strong, weak = evd.citation_strength("Person lifts the rear shutter in the alley", ["OBS-a", "OBS-b"], idx)
    assert strong == ["OBS-a"] and weak == ["OBS-b"]
    s2, w2 = evd.citation_strength("moves", ["OBS-b"], idx)
    assert s2 == ["OBS-b"] and w2 == [], "too little text to judge is not held against the citation"


def test_unsupported_time_mentions_are_found():
    cited = [4500]  # 01:15
    assert evd.time_mentions_unsupported("The shutter went up at 01:16 and again at 23:40", cited) == ["23:40"]
    assert evd.time_mentions_unsupported("no clock times here", cited) == []


def test_unresolved_conflict_marks_the_disputed_observations():
    ev = fake_ev()
    assert evd.disputed_observation_ids(ev) == {}, "resolved conflicts are settled"
    ev["conflicts"][0]["review_status"] = "unresolved"
    assert set(evd.disputed_observation_ids(ev)) == {"OBS-a", "OBS-b"}


def test_narrative_consistency_lists_facts_a_scenario_never_mentions():
    nar = {"supported_facts": ["The pharmacy shutter was forced open at the rear", "Cash register was emptied overnight"]}
    res = evd.narrative_consistency(nar, "Person forces the rear shutter and enters the pharmacy")
    assert res["available"] and len(res["facts_not_reflected"]) == 1 and "Cash" in res["facts_not_reflected"][0]
    assert evd.narrative_consistency(None, "x")["available"] is False


# ---------------------------------------------------------------- scoring

def _score(**kw):
    base = dict(llm_estimate=90, steps=[{"evidence_refs": ["OBS-a"], "strong_refs": ["OBS-a"]}, {"evidence_refs": ["OBS-b"], "strong_refs": ["OBS-b"]}],
                dropped=0, supporting=[{"refs": ["OBS-a", "OBS-b"]}], contradicted=[], hard_violations=0, observation_ids={"OBS-a", "OBS-b", "OBS-c"}, cautions=None)
    base.update(kw)
    return evd.score_scenario(**base)


def test_score_ignores_model_confidence_and_rewards_relevant_citations():
    assert _score(llm_estimate=10)["verifiable_score"] == _score(llm_estimate=99)["verifiable_score"]
    bare = _score(steps=[{"evidence_refs": [], "strong_refs": []}] * 2, supporting=[])
    assert _score()["verifiable_score"] > bare["verifiable_score"]
    weak = _score(steps=[{"evidence_refs": ["OBS-a"], "strong_refs": []}] * 2, supporting=[])
    assert weak["components"]["steps_citing_evidence"] == 0, "a weak citation does not count as support"


def test_score_penalties_are_itemised_and_capped():
    base = _score()["verifiable_score"]
    assert _score(contradicted=[{"refs": ["OBS-a"]}])["verifiable_score"] < base
    assert _score(dropped=3)["verifiable_score"] < base
    c = _score(cautions={"door_state": 1, "unsupported_time_mentions": 2, "weak_citations": 9})
    assert c["verifiable_score"] < base and c["components"]["caution_breakdown"] == {"door_state": 5, "unsupported_time_mentions": 6, "weak_citations": 6}
    capped = _score(hard_violations=1)
    assert capped["verifiable_score"] <= 25 and capped["cap_reason"]


def test_score_ignores_fake_observation_ids():
    fake = _score(steps=[{"evidence_refs": ["OBS-nope"], "strong_refs": ["OBS-nope"]}], supporting=[{"refs": ["OBS-nope"]}])
    assert fake["components"]["distinct_real_observations_cited"] == 0 and _score()["verifiable_score"] > fake["verifiable_score"]
