"""Through the API with a fake model: the prompt carries the open questions, near-copies are sent back once,
and every stored scenario says how it differs and how well supported it is."""
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from test_sandbox_api import CASE, client, layout_reply, state  # noqa: E402,F401
from pipeline import sandbox  # noqa: E402

PROMPTS = []
ATTEMPTS = {"n": 0}


def S(actor, node, action, dt=10, **kw):
    return {"actor": actor, "node_id": node, "action": action, "dt_sec_estimate": dt, "narrative": f"{actor} {action}", **kw}


def scenario(title, actors, steps, **kw):
    return {"title": title, "hypothesis_summary": "x", "plausibility_estimate": 70, "actors": actors,
            "supporting_facts": [{"text": "Rear shutter forced", "refs": ["OBS-T2"]}], "contradicted_points": [], "steps": steps, **kw}


REAR = [S("a", "exterior", "approach"), S("a", "rear", "damage", item="crowbar", effects=[{"target": "rear", "state": "forced"}], evidence_refs=["OBS-T2"]),
        S("a", "till", "take_item", item="cash", evidence_refs=["OBS-T3"]), S("a", "exterior", "flee")]
FRONT = [S("a", "front", "unlock", effects=[{"target": "front", "state": "unlocked"}]), S("a", "till", "take_item", item="cash", evidence_refs=["OBS-T3"]), S("a", "exterior", "flee")]
TWO = REAR + [S("b", "exterior", "wait"), S("b", "shelf", "search")]
ONE = [{"id": "a", "label": "Thief", "role": "suspect"}]
BOTH = ONE + [{"id": "b", "label": "Lookout", "role": "suspect"}]


def fake(system, prompt, max_tokens=2048, timeout=None):
    PROMPTS.append((system[:40], prompt))
    if "scene analyst" in system:
        out = layout_reply()
    elif "exactly 3 DIFFERENT" in system:
        ATTEMPTS["n"] += 1
        if ATTEMPTS["n"] == 1:   # three tellings of one story
            out = {"scenarios": [scenario(f"Same {i}", ONE, REAR) for i in range(3)]}
        else:
            out = {"scenarios": [scenario("Rear entry", ONE, REAR, differs_by="Best-supported reading: forced rear shutter."),
                                 scenario("Front door, unlocked", ONE, FRONT, differs_by="Came in by the front door.", less_supported=True),
                                 scenario("Two people", BOTH, TWO, differs_by="A second person took part.", less_supported=True)]}
    else:
        out = {"questions": []}
    return {"provider": "fake", "model": "fake-1", "parsed": out, "raw": json.dumps(out)}


@pytest.fixture()
def swapped_model(monkeypatch):
    PROMPTS.clear()
    ATTEMPTS["n"] = 0
    monkeypatch.setattr(sandbox, "chat_json_ex", fake)
    yield


def test_the_prompt_carries_the_open_questions_and_a_position_for_each_scenario(client, swapped_model):
    assert client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "full"}).status_code == 202
    d = state(client)
    assert d["status"] == "ready"
    first = next(p for sys_, p in PROMPTS if "Propose the 3 scenarios" in p)
    assert "OPEN QUESTIONS" in first and "Which outside door" in first and "Scenario 2: take the best-supported option" in first


def test_near_copies_are_sent_back_once_and_the_better_set_is_kept(client, swapped_model):
    client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "full"})
    d = state(client)
    assert ATTEMPTS["n"] == 2
    scen_prompts = [p for _, p in PROMPTS if "Propose the 3 scenarios" in p]
    assert len(scen_prompts) == 2 and "too repetitive" in scen_prompts[1]
    titles = {s["title"] for s in d["scenarios"]}
    assert titles == {"Rear entry", "Front door, unlocked", "Two people"}
    attempts = d["run"]["generation"]["diversity_attempts"] if "diversity_attempts" in d["run"].get("generation", {}) else None
    assert attempts and attempts[0]["near_duplicate_pairs"] > 0 and attempts[1]["near_duplicate_pairs"] == 0


def test_every_scenario_says_how_it_differs_and_how_well_supported_it_is(client, swapped_model):
    client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "full"})
    d = state(client)
    by_title = {s["title"]: s for s in d["scenarios"]}
    assert by_title["Rear entry"]["support_level"] in ("best_supported", "alternative") and by_title["Rear entry"]["differs_by"]
    assert by_title["Front door, unlocked"]["support_level"] == "less_supported"
    assert by_title["Two people"]["less_supported"] is True
    for s in d["scenarios"]:
        assert s["diversity"]["nearest_distance"] is not None and len(s["diversity"]["compared_with"]) == 2
        assert s["fidelity"]["round_trip_ok"] is True
        assert "coverage" in s and "key_observations" in s["coverage"]
    two = by_title["Two people"]
    assert any("number of people" in c["differs_in"] for c in two["diversity"]["compared_with"])


def test_the_open_questions_are_recorded_with_the_run(client, swapped_model):
    client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "full"})
    d = state(client)
    oq = d["run"]["generation"]["open_questions"]
    assert any(q["key"] == "entry" for q in oq)
