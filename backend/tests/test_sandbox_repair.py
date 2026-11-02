"""A scenario with a fixable logical problem gets one repair attempt; time conflicts with the evidence are left flagged."""
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from test_sandbox_api import CASE, client, layout_reply, state  # noqa: E402,F401
from pipeline import sandbox  # noqa: E402

CALLS = []


def S(actor, node, action, dt=10, **kw):
    return {"actor": actor, "node_id": node, "action": action, "dt_sec_estimate": dt, "narrative": f"{actor} {action}", **kw}


def scenario(title, actors, steps, **kw):
    return {"title": title, "hypothesis_summary": "x", "plausibility_estimate": 70, "actors": actors,
            "supporting_facts": [{"text": "Rear shutter forced", "refs": ["OBS-T2"]}], "contradicted_points": [], "steps": steps, **kw}


A = [{"id": "a", "label": "Thief", "role": "suspect"}]
AB = A + [{"id": "b", "label": "Partner", "role": "suspect"}]
REAR = [S("a", "exterior", "approach"), S("a", "rear", "damage", item="crowbar", effects=[{"target": "rear", "state": "forced"}]), S("a", "till", "take_item", item="cash"), S("a", "exterior", "flee")]
FRONT = [S("a", "front", "unlock", effects=[{"target": "front", "state": "unlocked"}]), S("a", "till", "take_item", item="cash"), S("a", "exterior", "flee")]
BROKEN = [S("a", "till", "take_item", item="cash"), S("a", "till", "hand_over", item="cash"), S("b", "shelf", "receive")]   # the receiver is in another room
FIXED = [S("a", "till", "take_item", item="cash"), S("a", "till", "hand_over", item="cash"), S("b", "till", "receive")]


def fake(system, prompt, max_tokens=2048, timeout=None):
    CALLS.append(system[:30])
    if "scene analyst" in system:
        out = layout_reply()
    elif "exactly 3 DIFFERENT" in system:
        out = {"scenarios": [scenario("Rear entry", A, REAR, differs_by="Best-supported."),
                             scenario("Front door", A, FRONT, differs_by="Front door.", less_supported=True),
                             scenario("Two people", AB, BROKEN, differs_by="A partner takes part.", less_supported=True)]}
    elif "repairing ONE" in system:
        assert "hands something over" in prompt and "not close by" in prompt   # it is told exactly what is wrong
        out = scenario("Two people", AB, FIXED, differs_by="A partner takes part.", less_supported=True)
    else:
        out = {"questions": []}
    return {"provider": "fake", "model": "fake-1", "parsed": out, "raw": json.dumps(out)}


@pytest.fixture()
def swapped(monkeypatch):
    CALLS.clear()
    monkeypatch.setattr(sandbox, "chat_json_ex", fake)


def test_a_fixable_problem_is_repaired_once_and_recorded(client, swapped):
    client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "full"})
    d = state(client)
    two = next(s for s in d["scenarios"] if s["title"] == "Two people")
    assert two["validation"]["is_physically_possible"] is True
    assert two["repair"]["problems_left"] == 0 and "not close by" in two["repair"]["problems_found"][0]
    assert any("repairing ONE" in c for c in CALLS) and sum(1 for c in CALLS if "repairing ONE" in c) == 1
    rep = d["run"]["generation"]["repairs"]
    assert rep[0]["fixed"] is True


def test_scenarios_with_no_problem_are_never_sent_for_repair(client, swapped):
    client.post(f"/cases/{CASE}/sandbox/generate", json={"mode": "full"})
    d = state(client)
    for s in d["scenarios"]:
        if s["title"] != "Two people":
            assert "repair" not in s
