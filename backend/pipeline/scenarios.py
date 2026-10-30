"""
Stage 9 — Scenario Comparison. Generates alternative explanations from the
real conflict content via the LLM fallback chain (Meta -> Groq -> Gemini).
Not a fixed template — the scenarios are grounded in the specific claims and
sources of each detected conflict.
"""
import time

from llm_client import chat_json, LLMUnavailableError

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


def generate_scenarios(conflicts: list):
    if not conflicts:
        return []

    all_scenarios = []
    providers_used = set()
    for c in conflicts:
        prompt = (
            f"Claim A (source {c['source_a']}, time {c['time_a']}): {c['claim_a']}\n\n"
            f"Claim B (source {c['source_b']}, time {c['time_b']}): {c['claim_b']}\n\n"
            f"Nature of conflict: {c.get('nature_of_conflict', '')}"
        )
        try:
            provider, scenarios = chat_json(SYSTEM_PROMPT, prompt)
        except LLMUnavailableError as e:
            raise LLMUnavailableError(
                f"Scenario generation failed: {e}\n"
                f"Set at least one of META_API_KEY / GROQ_API_KEY / GOOGLE_API_KEY in backend/.env"
            ) from e
        providers_used.add(provider)
        # Tolerate {"scenarios": [...]} or a single object instead of a bare array.
        if isinstance(scenarios, dict):
            lists = [v for v in scenarios.values() if isinstance(v, list)]
            scenarios = lists[0] if lists else [scenarios]
        all_scenarios.extend(s for s in scenarios if isinstance(s, dict))
        time.sleep(2)

    return all_scenarios
