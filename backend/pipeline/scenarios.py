"""
Stage 9 — Scenario Comparison. Generates alternative explanations from the
real conflict content via the LLM fallback chain (Meta -> local -> Groq -> Gemini).
Not a fixed template — the scenarios are grounded in the specific claims and
sources of each detected conflict. Model output is read defensively (see llm_schema)
and identifiers are redacted before the text is sent (see llm_guard).
"""
import os
import time

from llm_client import LLMUnavailableError
from pipeline import llm_schema as sch
from pipeline.llm_guard import case_redactor, safe_chat_json

SYSTEM_PROMPT = """You are a scenario-comparison assistant for CaseWeave, an
investigation support tool. Given a detected conflict between two evidence
claims, propose 2-4 plausible alternative explanations for why the sources
disagree. Do not assign guilt, innocence, or probabilities. Each scenario
must state what it assumes and which evidence supports vs challenges it.

Respond with ONLY a JSON array of objects with exactly these keys:
- name: short scenario title
- assumption: what this scenario assumes to be true
- supporting_evidence: what in the case supports this scenario
- challenging_evidence: what in the case challenges or complicates it
No prose, no markdown fences, no commentary."""


def _clean(s: dict, conflict_id: str | None) -> dict | None:
    name = sch.text(s.get("name"), 200)
    assumption = sch.text(s.get("assumption"), 1500)
    if not name and not assumption:
        return None
    return {
        "name": name or "Unnamed scenario",
        "assumption": assumption or "—",
        "supporting_evidence": sch.text(s.get("supporting_evidence"), 1500) or "—",
        "challenging_evidence": sch.text(s.get("challenging_evidence"), 1500) or "—",
        "conflict_id": conflict_id,
    }


def generate_scenarios(conflicts: list, case_id: str | None = None):
    if not conflicts:
        return []

    all_scenarios = []
    redactor = case_redactor(case_id)
    pacing = float(os.environ.get("LLM_CALL_PACING_S", "1"))
    for c in conflicts:
        prompt = (
            f"Claim A (source {c['source_a']}, time {c['time_a']}): {c['claim_a']}\n\n"
            f"Claim B (source {c['source_b']}, time {c['time_b']}): {c['claim_b']}\n\n"
            f"Nature of conflict: {c.get('nature_of_conflict', '')}"
        )
        for attempt in range(2):
            try:
                _, scenarios = safe_chat_json(case_id, SYSTEM_PROMPT, prompt, redactor=redactor)
                break
            except LLMUnavailableError as e:
                if "non-JSON" in str(e) and attempt == 0:
                    continue
                raise LLMUnavailableError(
                    f"Scenario generation failed: {e}\n"
                    f"Set at least one of META_API_KEY / GROQ_API_KEY / GOOGLE_API_KEY in backend/.env"
                ) from e
        all_scenarios.extend(x for x in (_clean(s, c.get("conflict_id")) for s in sch.records(scenarios)) if x)
        if pacing:
            time.sleep(pacing)

    return all_scenarios
