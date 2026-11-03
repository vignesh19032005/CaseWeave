"""Tool-calling through Meta's Model API: the model proposes, our checker decides.

Repair used to be one shot: the model rewrote a scenario once and we hoped. Here the model is given a tool, `check_scenario`, that runs the
deterministic geometry engine and validator on whatever it proposes and reports what is still wrong. It can fix and re-check a few times, and
the answer we keep is whichever version the checker (not the model) says has fewer problems. The model never decides whether a scenario is possible.

This uses the function-calling support of Meta's Model API (`/v1/responses`, `function_call` and `function_call_output` items). It is used only when
Meta models are allowed (not in `local_only` mode); otherwise the single-shot repair in sandbox.py is used, so nothing depends on it.
"""
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List

import llm_client

logger = logging.getLogger("caseweave.sandbox_agent")

MAX_TURNS = 5            # model replies, including the last one that holds the answer
MAX_TOOL_CALLS = 4
MODEL = "muse-wonder-1.0"


def enabled() -> bool:
    """On unless switched off with SANDBOX_AGENT_REPAIR=0, and never in local_only mode (that is the on-premise promise)."""
    if os.environ.get("SANDBOX_AGENT_REPAIR", "1").strip() in ("0", "false", "no"):
        return False
    return llm_client.provider_mode() != "local_only"


def _key() -> str:
    key = os.environ.get("META_API_KEY", "").strip()
    if not key:
        try:
            from secrets_store import get_secret
            key = (get_secret("META_API_KEY") or "").strip()
        except Exception:  # noqa: BLE001
            key = ""
    return key


def _text_of(output: List[Dict[str, Any]]) -> str:
    parts = []
    for item in output:
        if item.get("type") == "message":
            for block in item.get("content", []):
                if block.get("type") == "output_text":
                    parts.append(block.get("text", ""))
    return "\n".join(parts).strip()


def meta_tool_loop(system: str, user: str, tools: List[Dict[str, Any]], run_tool: Callable[[str, Dict[str, Any]], Dict[str, Any]],
                   max_turns: int = MAX_TURNS, max_tool_calls: int = MAX_TOOL_CALLS, timeout: int = 240) -> Dict[str, Any]:
    """Runs the function-calling conversation. Returns {"text", "tool_calls": [{"name","args_chars","result"}], "seconds", "turns", "model"}.
    Raises llm_client.LLMUnavailableError if Meta cannot be reached or gives nothing usable."""
    key = _key()
    if not key:
        raise llm_client.LLMUnavailableError("META_API_KEY not set")
    base = os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1").strip()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    history: List[Dict[str, Any]] = [{"role": "user", "content": f"{system}\n\n{user}"}]
    log: List[Dict[str, Any]] = []
    started = time.time()
    text = ""
    for turn in range(1, max_turns + 1):
        payload: Dict[str, Any] = {"model": MODEL, "input": history, "reasoning": {"effort": "high"}}
        if len(log) < max_tool_calls:
            payload["tools"] = tools
        result = llm_client._post_json(f"{base}/responses", headers, payload, timeout=timeout, retries=2)
        output = result.get("output", [])
        calls = [o for o in output if o.get("type") == "function_call"]
        history.extend(output)
        text = _text_of(output)
        if not calls:
            return {"text": text, "tool_calls": log, "seconds": round(time.time() - started, 1), "turns": turn, "model": MODEL}
        for call in calls:
            try:
                args = json.loads(call.get("arguments") or "{}")
            except ValueError:
                args = {}
            try:
                res = run_tool(call.get("name", ""), args if isinstance(args, dict) else {})
            except Exception as e:  # noqa: BLE001 - a tool error is reported to the model, not raised
                res = {"error": str(e)[:200]}
            log.append({"name": call.get("name"), "args_chars": len(call.get("arguments") or ""), "result": res})
            history.append({"type": "function_call_output", "call_id": call.get("call_id"), "output": json.dumps(res, default=str)[:6000]})
    return {"text": text, "tool_calls": log, "seconds": round(time.time() - started, 1), "turns": max_turns, "model": MODEL}


CHECK_TOOL = {
    "type": "function",
    "name": "check_scenario",
    "description": ("Runs CaseWeave's deterministic checker on a full scenario (the same JSON shape you were given). It lays the steps out in the real "
                    "building, walks every person along real routes, and reports what is still physically or logically impossible, plus the "
                    "evidence-support score. Call it with your corrected scenario, read the problems, fix, and call again."),
    "parameters": {"type": "object", "properties": {"scenario": {"type": "object", "description": "the complete scenario JSON"}}, "required": ["scenario"]},
}
