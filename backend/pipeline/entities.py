"""
Stage 11 — Entity Resolution + Relationship Graph. Builds on Stage 2a's
subject/location fields. Dedup/alias-matching is LLM-assisted (handles
"R. Kumaran" vs "Kumaran" vs "the witness" referring to the same person),
relationships are derived directly from each observation's subject->action
(at location), not invented separately.
"""
import uuid

from db import get_conn, append_audit_event
from llm_client import chat_json, LLMUnavailableError

DEDUP_SYSTEM_PROMPT = """You are an entity resolution assistant for
CaseWeave. You are given a list of raw subject/location mentions extracted
from case evidence. Group mentions that refer to the SAME real-world entity
(person, device, or place) together, accounting for aliases, partial names,
and referring phrases (e.g. "R. Kumaran", "Kumaran", "the witness near the
gate" could be the same person if context supports it — but do NOT merge
different people just because both are "a witness").

Respond with ONLY a JSON array of objects:
[{"canonical_name": "", "entity_type": "person|device|location|organization",
  "aliases": ["", ...]}]
Every input mention must appear in exactly one group's aliases list
(include the canonical name itself in aliases). No prose, no markdown
fences."""


def resolve_entities(case_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT observation_id, subject, location FROM observations WHERE case_id=?",
        (case_id,),
    )
    rows = cur.fetchall()

    mentions = []  # (text, type, observation_id)
    for r in rows:
        if r["subject"]:
            mentions.append((r["subject"], "person_or_device", r["observation_id"]))
        if r["location"]:
            mentions.append((r["location"], "location", r["observation_id"]))

    if not mentions:
        conn.close()
        return {"entities": [], "relationships": []}

    unique_texts = sorted(set(m[0] for m in mentions))
    prompt = "Mentions to resolve:\n" + "\n".join(f"- {t}" for t in unique_texts)

    try:
        provider, groups = chat_json(DEDUP_SYSTEM_PROMPT, prompt, max_tokens=2048)
    except LLMUnavailableError as e:
        conn.close()
        raise LLMUnavailableError(f"Entity resolution failed: {e}") from e

    # map each raw mention text -> entity_id
    text_to_entity = {}
    entities = []
    for g in groups:
        entity_id = f"ENT-{uuid.uuid4().hex[:8]}"
        entities.append(
            {
                "entity_id": entity_id,
                "canonical_name": g.get("canonical_name", ""),
                "entity_type": g.get("entity_type", "unknown"),
                "aliases": g.get("aliases", []),
            }
        )
        for alias in g.get("aliases", []):
            text_to_entity[alias] = entity_id

    cur.execute("DELETE FROM entities WHERE case_id=?", (case_id,))
    cur.execute("DELETE FROM entity_mentions WHERE case_id=?", (case_id,))
    cur.execute("DELETE FROM relationships WHERE case_id=?", (case_id,))

    for e in entities:
        cur.execute(
            "INSERT INTO entities VALUES (?,?,?,?,?)",
            (e["entity_id"], case_id, e["canonical_name"], e["entity_type"], ",".join(e["aliases"])),
        )

    for text, mtype, obs_id in mentions:
        entity_id = text_to_entity.get(text)
        if entity_id:
            cur.execute(
                "INSERT INTO entity_mentions VALUES (?,?,?,?,?)",
                (f"MEN-{uuid.uuid4().hex[:8]}", case_id, entity_id, obs_id, text),
            )

    # relationships: subject --action--> location, derived straight from each observation
    cur.execute(
        "SELECT observation_id, subject, action, location FROM observations WHERE case_id=? AND subject IS NOT NULL AND location IS NOT NULL",
        (case_id,),
    )
    relationships = []
    for r in cur.fetchall():
        from_id = text_to_entity.get(r["subject"])
        to_id = text_to_entity.get(r["location"])
        if from_id and to_id:
            rel_id = f"REL-{uuid.uuid4().hex[:8]}"
            rel_type = r["action"] or "associated_with"
            cur.execute(
                "INSERT INTO relationships VALUES (?,?,?,?,?,?)",
                (rel_id, case_id, from_id, to_id, rel_type, r["observation_id"]),
            )
            relationships.append(
                {"relationship_id": rel_id, "from": from_id, "to": to_id, "type": rel_type, "source": r["observation_id"]}
            )

    conn.commit()
    append_audit_event(conn, case_id, "system", "entity_resolution_run", case_id)
    conn.close()

    return {"entities": entities, "relationships": relationships}
