"""
Stage 9a — Cross-Evidence Incident Reconstruction. Generalizes Stage 9's
per-conflict Scenario Comparison into one synthesized narrative across the
whole case: timeline + entity graph + conflicts + evidence links. Needs
Stage 11 (entities.py) to have run first — the entity/relationship context
is what makes this a reconstruction rather than a restated timeline.
"""
from llm_client import chat_json, LLMUnavailableError

SYSTEM_PROMPT = """You are an incident reconstruction assistant for
CaseWeave, an investigation support tool. Given a case's full timeline,
known entities and their relationships, detected conflicts, and evidence
links, produce ONE synthesized reconstruction of what the evidence
supports. You must NOT invent events the evidence doesn't support, and you
must explicitly flag unresolved gaps rather than smoothing over them.

For each unresolved gap, also give your best-guess answer grounded in what
IS in the evidence (never outside information) and how confident that guess
is. A gap with no reasonable inference at all should get guess: null and
confidence: "none" — do not force a guess where the evidence gives no basis
for one.

Respond with ONLY a JSON object with exactly these keys:
- narrative: 3-6 sentences describing the reconstructed sequence of events,
  citing source_evidence_ids inline in parentheses
- supported_facts: array of short strings, each a fact the evidence
  directly supports
- unresolved_gaps: array of objects, each with exactly these keys:
  - question: the specific open question the evidence does NOT resolve
  - best_guess: your most defensible inference from the evidence, as a
    short sentence, or null if the evidence gives no reasonable basis to
    guess
  - confidence: one of "low" | "medium" | "high" | "none" (none only when
    best_guess is null) — reflects how strongly the AVAILABLE evidence
    (not outside knowledge) supports the guess
  - basis: one short phrase citing which evidence the guess leans on, or
    null if best_guess is null
- confidence_note: one sentence on the overall reliability of this
  reconstruction given the conflicts/gaps found
No prose outside the JSON, no markdown fences."""


def reconstruct_incident(case_id: str, timeline_events: list, entities: list, relationships: list, conflicts: list, evidence_links: list):
    timeline_text = "\n".join(
        f"- {e['time']} [{e['classification']}] {e['description']} (source: {e['source_evidence_id']})"
        for e in timeline_events
    )
    entities_text = "\n".join(
        f"- {e['canonical_name']} ({e['entity_type']})" for e in entities
    ) or "(none resolved)"
    relationships_text = "\n".join(
        f"- {r['from']} --{r['type']}--> {r['to']}" for r in relationships
    ) or "(none)"
    conflicts_text = "\n".join(
        f"- CONFLICT: {c['claim_a']} vs {c['claim_b']} ({c.get('nature_of_conflict', '')})" for c in conflicts
    ) or "(none detected)"
    links_text = "\n".join(
        f"- {l['link_type'].upper()}: {l['claim_a']} <-> {l['claim_b']}" for l in evidence_links
    ) or "(none)"

    prompt = (
        f"TIMELINE:\n{timeline_text}\n\n"
        f"ENTITIES:\n{entities_text}\n\n"
        f"RELATIONSHIPS:\n{relationships_text}\n\n"
        f"CONFLICTS:\n{conflicts_text}\n\n"
        f"EVIDENCE LINKS:\n{links_text}\n\n"
        f"Produce the reconstruction."
    )

    try:
        provider, result = chat_json(SYSTEM_PROMPT, prompt, max_tokens=1536)
    except LLMUnavailableError as e:
        raise LLMUnavailableError(f"Incident reconstruction failed: {e}") from e

    gaps = []
    for g in result.get("unresolved_gaps", []):
        if isinstance(g, str):
            # Tolerate a model that ignores the object schema and returns
            # plain strings — degrade gracefully instead of dropping the gap.
            gaps.append({"question": g, "best_guess": None, "confidence": "none", "basis": None})
        elif isinstance(g, dict):
            gaps.append(
                {
                    "question": g.get("question", ""),
                    "best_guess": g.get("best_guess"),
                    "confidence": g.get("confidence", "none") if g.get("best_guess") else "none",
                    "basis": g.get("basis"),
                }
            )

    return {
        "narrative": result.get("narrative", ""),
        "supported_facts": result.get("supported_facts", []),
        "unresolved_gaps": gaps,
        "confidence_note": result.get("confidence_note", ""),
        "provider": provider,
    }
