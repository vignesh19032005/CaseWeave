"""Tool-calling repair through Meta's API: the model proposes, the checker decides. The model API is faked; no network, no database."""
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import llm_client  # noqa: E402
from pipeline import sandbox, sandbox_agent  # noqa: E402


def _msg(text):
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


def _call(args, name="check_scenario", cid="call_1"):
    return {"type": "function_call", "call_id": cid, "name": name, "arguments": json.dumps(args)}


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("META_API_KEY", "test-key")
    monkeypatch.delenv("LLM_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("SANDBOX_AGENT_REPAIR", raising=False)


def test_the_tool_result_goes_back_to_the_model_and_the_final_text_is_returned(monkeypatch):
    sent = []

    def fake_post(url, headers, payload, timeout=60, retries=3):
        sent.append(payload)
        if len(sent) == 1:
            assert payload["tools"][0]["name"] == "check_scenario"
            return {"output": [{"type": "reasoning"}, _call({"scenario": {"title": "x"}})]}
        return {"output": [_msg('{"title": "fixed"}')]}

    monkeypatch.setattr(llm_client, "_post_json", fake_post)
    seen = []
    res = sandbox_agent.meta_tool_loop("sys", "user", [sandbox_agent.CHECK_TOOL], lambda n, a: (seen.append((n, a)), {"problems_to_fix": 0})[1])
    assert seen == [("check_scenario", {"scenario": {"title": "x"}})]
    assert res["text"] == '{"title": "fixed"}' and len(res["tool_calls"]) == 1 and res["turns"] == 2
    outputs = [h for h in sent[1]["input"] if isinstance(h, dict) and h.get("type") == "function_call_output"]
    assert outputs and json.loads(outputs[0]["output"]) == {"problems_to_fix": 0} and outputs[0]["call_id"] == "call_1"


def test_a_tool_that_raises_is_reported_to_the_model_not_raised(monkeypatch):
    replies = iter([{"output": [_call({"scenario": {}})]}, {"output": [_msg("done")]}])
    monkeypatch.setattr(llm_client, "_post_json", lambda *a, **k: next(replies))

    def boom(name, args):
        raise ValueError("bad thing")

    res = sandbox_agent.meta_tool_loop("s", "u", [sandbox_agent.CHECK_TOOL], boom)
    assert res["text"] == "done" and res["tool_calls"][0]["result"] == {"error": "bad thing"}


def test_the_number_of_checks_is_capped(monkeypatch):
    n = {"calls": 0}

    def always_call(url, headers, payload, timeout=60, retries=3):
        n["calls"] += 1
        return {"output": [_call({"scenario": {}}, cid=f"c{n['calls']}")] if "tools" in payload else [_msg("stop")]}

    monkeypatch.setattr(llm_client, "_post_json", always_call)
    res = sandbox_agent.meta_tool_loop("s", "u", [sandbox_agent.CHECK_TOOL], lambda n_, a: {"ok": 1}, max_turns=9, max_tool_calls=2)
    assert len(res["tool_calls"]) == 2 and res["text"] == "stop"


def test_it_is_off_for_local_only_and_when_switched_off(monkeypatch):
    assert sandbox_agent.enabled() is True
    monkeypatch.setenv("LLM_PROVIDER_MODE", "local_only")
    assert sandbox_agent.enabled() is False
    monkeypatch.setenv("LLM_PROVIDER_MODE", "meta_only")
    assert sandbox_agent.enabled() is True
    monkeypatch.setenv("SANDBOX_AGENT_REPAIR", "0")
    assert sandbox_agent.enabled() is False


def test_no_key_means_unavailable(monkeypatch):
    monkeypatch.delenv("META_API_KEY", raising=False)
    monkeypatch.setattr(sandbox_agent, "_key", lambda: "")
    with pytest.raises(llm_client.LLMUnavailableError):
        sandbox_agent.meta_tool_loop("s", "u", [], lambda n, a: {})


class _Redactor:
    def redact(self, t):
        return t

    def restore_json(self, o):
        return o

    def summary(self):
        return {"enabled": False}


def _built(n_problems, score=50):
    return {"validation": {"is_physically_possible": n_problems == 0, "violations": [{"code": "locked_door_passed", "message": "m"}] * n_problems},
            "score": {"verifiable_score": score}}


def test_the_version_the_checker_likes_best_is_kept_not_the_last_one_the_model_wrote(monkeypatch):
    versions = {"a": _built(3), "b": _built(1), "c": _built(2)}
    monkeypatch.setattr(sandbox, "_build_scenario", lambda raw, layout, ev, ctx: versions[raw["id"]])

    def fake_loop(system, user, tools, run_tool, **kw):
        run_tool("check_scenario", {"scenario": {"id": "a"}})
        run_tool("check_scenario", {"scenario": {"id": "b"}})
        return {"text": '{"id": "c"}', "tool_calls": [{"name": "check_scenario", "result": {"problems_to_fix": 3}}, {"name": "check_scenario", "result": {"problems_to_fix": 1}}],
                "seconds": 1.0, "turns": 3, "model": "m"}

    monkeypatch.setattr(sandbox_agent, "meta_tool_loop", fake_loop)
    meta = {"calls": []}
    entry = {}
    best = sandbox._agent_repair({"id": "orig"}, [{"message": "p"}], {"locked_door_passed"}, {}, {}, {}, _Redactor(), meta, "C", "", "", entry)
    assert len(best["validation"]["violations"]) == 1
    assert entry["method"] == "tool_calling" and len(entry["tool_calls"]) == 2
    assert meta["calls"][0]["method"] == "tool_calling" and meta["calls"][0]["provider"] == "meta"


def test_if_the_agent_cannot_run_the_single_shot_repair_takes_over(monkeypatch):
    def down(*a, **k):
        raise llm_client.LLMUnavailableError("down")

    monkeypatch.setattr(sandbox_agent, "meta_tool_loop", down)
    entry = {}
    assert sandbox._agent_repair({}, [{"message": "p"}], set(), {}, {}, {}, _Redactor(), {"calls": []}, "C", "", "", entry) is None
    assert "single_shot" in entry["method"]
