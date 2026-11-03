"""If no scenario is strongly supported, the best one is improved once with the evidence it left unused; the score formula is never touched."""
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from test_sandbox_api import CASE, client, layout_reply, state  # noqa: E402,F401
from pipeline import sandbox  # noqa: E402

CALLS = []
MODE = {"improve": "better"}


def S(actor, node, action, dt=10, **kw):
    return {"actor": actor, "node_id": node, "action": action, "dt_sec_estimate": dt, "narrative": f"{actor} {action}", **kw}


def scenario(title, steps, facts=True, **kw):
    return {"title": title, "hypothesis_summary": "x", "plausibility_estimate": 70, "actors": [{"id": "a", "label": "Thief", "role": "suspect"}],
            "supporting_facts": [{"text": "Rear shutter forced", "refs": ["OBS-T2"]}] if facts else [], "contradicted_points": [], "steps": steps, **kw}


WEAK = [S("a", "exterior", "approach"), S("a", "rear", "damage", item="crowbar", effects=[{"target": "rear", "state": "forced"}]), S("a", "till", "take_item", item="cash"), S("a", "exterior", "flee")]
STRONG = [S("a", "exterior", "approach", narrative="Approaches the front door that was locked", evidence_refs=["OBS-T1"]),
          S("a", "rear", "damage", item="crowbar", narrative="Forces the rear shutter", evidence_refs=["OBS-T2"], effects=[{"target": "rear", "state": "forced"}]),
          S("a", "till", "take_item", item="cash", narrative="Till emptied of cash", evidence_refs=["OBS-T3"]),
          S("a", "exterior", "flee", narrative="Leaves, an untimed note records it", evidence_refs=["OBS-T4"])]
FRONT = [S("a", "front", "unlock", effects=[{"target": "front", "state": "unlocked"}]), S("a", "till", "take_item", item="cash"), S("a", "exterior", "flee")]
OTHER = [S("a", "exterior", "approach"), S("a", "front", "open"), S("a", "safe", "search"), S("a", "till", "take_item", item="cash")]


def fake(system, prompt, max_tokens=2048, timeout=None):
    CALLS.append(system[:34])
    if "scene analyst" in system:
        out = layout_reply()
    elif "exactly 3 DIFFERENT" in system:
        out = {"scenarios": [scenario("Rear entry", WEAK, differs_by="main", facts=False), scenario("Front door", FRONT, differs_by="front", less_supported=True, facts=False),
                             scenario("Other order", OTHER, differs_by="order", less_supported=True, facts=False)]}
    elif "improving ONE" in system:
        assert "NOT YET USED" in prompt or "steps cite evidence" in prompt
        out = scenario("Rear entry", STRONG if MODE["improve"] == "better" else WEAK, differs_by="main", facts=MODE["improve"] == "better")
    else:
        out = {"questions": []}
    return {"provider": "fake", "model": "fake-1", "parsed": out, "raw": json.dumps(out)}


@pytest.fixture()
def swapped(monkeypatch):
    CALLS.clear()
    MODE["improve"] = "better"
    monkeypatch.setattr(sandbox, "chat_json_ex", fake)


def test_a_weak_best_scenario_is_improved_once_and_the_gain_comes_from_real_citations(client, swapped):
    client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "full"})
    d = state(client)
    top = d["scenarios"][0]
    gen = d["run"]["generation"]
    assert gen["strengthen"]["applied"] is True and gen["strengthen"]["to_score"] > gen["strengthen"]["from_score"]
    assert top["title"] == "Rear entry" and top["strengthened"]["to_score"] == top["score"]["verifiable_score"] >= sandbox.STRONG_SCORE
    assert top["score"]["components"]["steps_citing_evidence"] == 4 and sum(1 for c in CALLS if "improving ONE" in c) == 1
    assert d["run"]["generation"]["best_score"] == top["score"]["verifiable_score"]


def test_an_improved_version_that_is_not_better_is_not_used(client, swapped):
    MODE["improve"] = "same"
    client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "full"})
    d = state(client)
    gen = d["run"]["generation"]
    assert gen["strengthen"]["applied"] is False
    assert not any("strengthened" in s for s in d["scenarios"])
    assert gen["best_score"] < sandbox.STRONG_SCORE        # and it says so honestly instead of lifting the number


def test_a_strong_scenario_is_left_alone(client, monkeypatch):
    CALLS.clear()

    def strong_fake(system, prompt, max_tokens=2048, timeout=None):
        CALLS.append(system[:34])
        if "exactly 3 DIFFERENT" in system:
            return {"provider": "fake", "model": "fake-1", "raw": "{}", "parsed": {"scenarios": [scenario("Rear entry", STRONG, differs_by="main"), scenario("Front door", FRONT, differs_by="front", less_supported=True, facts=False),
                                                                                                       scenario("Other", OTHER, differs_by="order", less_supported=True, facts=False)]}}
        return fake(system, prompt, max_tokens, timeout)

    monkeypatch.setattr(sandbox, "chat_json_ex", strong_fake)
    client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "full"})
    d = state(client)
    assert not any("improving ONE" in c for c in CALLS) and "strengthen" not in d["run"]["generation"]
    assert max(s["score"]["verifiable_score"] for s in d["scenarios"]) >= sandbox.STRONG_SCORE


def test_the_score_formula_itself_is_unchanged_by_all_this():
    from pipeline import sandbox_evidence as evd
    steps = [{"strong_refs": ["OBS-1"], "evidence_refs": ["OBS-1"]} for _ in range(4)]
    sc = evd.score_scenario(llm_estimate=50, steps=steps, dropped=0, supporting=[{"refs": ["OBS-2", "OBS-3"]}], contradicted=[], hard_violations=0, observation_ids={"OBS-1", "OBS-2", "OBS-3"})
    assert sc["verifiable_score"] == round(100 * (0.45 * 1 + 0.35 * 3 / 6 + 0.20 * 1))
    assert evd.score_scenario(llm_estimate=99, steps=steps, dropped=0, supporting=[], contradicted=[], hard_violations=2, observation_ids={"OBS-1"})["verifiable_score"] <= 25


def test_an_open_question_costs_less_than_a_fact_that_contradicts_and_unmarked_points_count_as_contradictions():
    from pipeline import sandbox_evidence as evd
    steps = [{"strong_refs": ["OBS-1"], "evidence_refs": ["OBS-1"]} for _ in range(4)]
    kw = dict(llm_estimate=50, steps=steps, dropped=0, supporting=[{"refs": ["OBS-2", "OBS-3"]}], hard_violations=0, observation_ids={"OBS-1", "OBS-2", "OBS-3"})
    none = evd.score_scenario(contradicted=[], **kw)["verifiable_score"]
    contra = evd.score_scenario(contradicted=[{"refs": ["OBS-1"], "kind": "contradicts"}], **kw)
    openq = evd.score_scenario(contradicted=[{"refs": ["OBS-1"], "kind": "open_question"}], **kw)
    unmarked = evd.score_scenario(contradicted=[{"refs": ["OBS-1"]}], **kw)
    assert none - contra["verifiable_score"] == 8 and none - openq["verifiable_score"] == 2 and unmarked["verifiable_score"] == contra["verifiable_score"]
    assert openq["components"]["open_questions"] == 1 and openq["components"]["contradictions"] == 0
    many = evd.score_scenario(contradicted=[{"refs": ["OBS-1"], "kind": "contradicts"}] * 10, **kw)
    assert none - many["verifiable_score"] == 30           # the cap is unchanged


def test_the_kind_a_model_gives_survives_cleaning_and_replanning():
    from pipeline import sandbox_evidence as evd
    out = evd.clean_facts([{"text": "Identity is not established", "refs": ["OBS-T1"], "kind": "open_question"}, {"text": "The door was locked", "refs": ["OBS-T1"]}, "plain text"], {"OBS-T1"})
    assert [f["kind"] for f in out] == ["open_question", "contradicts", "contradicts"]
