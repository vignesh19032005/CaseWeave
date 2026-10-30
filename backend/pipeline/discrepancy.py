"""
Stage 4 — Discrepancy Detection, via structured 3-agent debate.

Why debate instead of a single adjudication call: measured directly on this
project's own test case — a single holistic judgment call caught the real
planted conflict only 1-in-4 times at low reasoning effort, and 0-in-3 at
high effort (more reasoning time made it MORE willing to explain the
conflict away, not less). The task itself is genuinely ambiguous to a
single pass: a device timestamp and a human estimate 6 minutes apart is a
defensible "different events" read in isolation. Forcing explicit argument
for both sides before a verdict — the same reason real investigative teams
have someone argue devil's advocate — surfaces considerations a single
pass skips, and is a well-established technique for exactly this kind of
ambiguous-judgment reliability problem (self-consistency via structured
disagreement, not just resampling the same prompt).

Three real roles, not a relabeled single call:
1. PROSECUTOR — a case analyst whose job is building the strongest possible
   argument that two claims describe the same event with a genuine
   discrepancy. Argues to convince, not to summarize.
2. DEFENDER — a case analyst whose job is building the strongest possible
   argument that the claims are compatible / describe different events /
   the apparent conflict doesn't hold up. Also argues to convince.
3. JUDGE — reads both arguments plus the shared evidence and entity-
   resolution context, and rules — citing which argument was more
   evidence-grounded, not just picking a side by vibe.

Entity-resolution grounding (Stage 11, now run BEFORE Stage 4): if both
claims already resolve to the same canonical entity/location, that's
handed to all three agents as an established fact, not something they have
to infer — removing one whole axis of legitimate ambiguity.
"""
import json
import time
import uuid
from collections import Counter

from db import get_conn, append_audit_event
from llm_client import chat_json, LLMUnavailableError

TOPIC_KEYWORDS = ["door", "enter", "open", "entrance", "inside"]

DECISION_RUBRIC = """DECISION RUBRIC (apply this, do not substitute your own):
- If both claims describe the same type of event (e.g. an entry, an
  opening, an arrival) AND they resolve to the same entity/location AND no
  third piece of evidence independently confirms them as two separate
  occurrences, treat them as describing ONE real-world event — any
  difference in reported time, description, or detail between them is a
  genuine CONFLICT to flag, not a reason to call them unrelated events.
- A timestamp gap alone is NOT grounds to call two claims "different
  events." A device log and a human estimate describing the same kind of
  event at the same location, even 15-30 minutes apart, should default to
  SAME event with a timing discrepancy, unless the evidence explicitly
  supports a second distinct occurrence (e.g. a log shows two separate
  entries and only one is corroborated elsewhere).
- Only classify as "related_to" or "unrelated" if there is a concrete,
  evidence-based reason to believe these describe different occurrences —
  not merely because reconciling them requires judgment."""

PROSECUTOR_SYSTEM_PROMPT = f"""You are a senior case analyst for CaseWeave,
an investigation support tool. Your specific role on this review is
PROSECUTOR: you build the strongest possible case that the two claims you
are given describe the SAME real-world event and that a genuine conflict
exists between them. You are not neutral — your job is advocacy grounded
in the evidence, the same way a real investigator stress-tests a theory by
arguing it as hard as possible before trusting it.

{DECISION_RUBRIC}

Given the two claims (and any entity-resolution context establishing they
share a location/entity), write your strongest argument for why these
describe the same event and constitute a real, flaggable discrepancy. Cite
the rubric where it applies. Be specific about what exactly conflicts
(time, description, sequence).

Respond with ONLY a JSON object: {{"argument": "<your case, 2-4
sentences>", "proposed_verification_question": "<what an investigator
should check next if this is a real conflict>"}}. No prose outside the
JSON, no markdown fences."""

DEFENDER_SYSTEM_PROMPT = f"""You are a senior case analyst for CaseWeave,
an investigation support tool. Your specific role on this review is
DEFENDER: you build the strongest possible case that the two claims you
are given are compatible, or describe different events, or that the
apparent conflict does not actually hold up under scrutiny. You are not
neutral — your job is to find the real, evidence-grounded reasons the
Prosecutor's theory might be wrong, the same way a real investigator
avoids jumping to conclusions from a surface-level read.

{DECISION_RUBRIC}

Note: the rubric above sets a real bar — "it's possible they're different"
is not enough on its own; you need a concrete, evidence-based reason, not
just general uncertainty. If you cannot find one, say so honestly rather
than manufacturing doubt.

Respond with ONLY a JSON object: {{"argument": "<your case, 2-4
sentences, or an honest statement that no real counter-argument exists>"}}.
No prose outside the JSON, no markdown fences."""

JUDGE_SYSTEM_PROMPT = f"""You are the senior reviewing analyst for
CaseWeave, an investigation support tool. You have two colleagues' written
arguments about whether two evidence claims describe the same event with a
genuine conflict: one argued FOR (Prosecutor), one argued AGAINST
(Defender). Your job is to rule, based on which argument is actually more
grounded in the evidence and the rubric below — not by splitting the
difference, and not by default leniency. If the Defender's counter-
argument is not concretely evidence-based (e.g. it only asserts general
uncertainty without a specific fact), rule for the Prosecutor.

{DECISION_RUBRIC}

Respond with ONLY a JSON object with exactly these keys:
- relationship: one of conflicts | supports | related_to | unrelated
- reason: one sentence citing which argument was more evidence-grounded
  and why
- verification_question: a specific, actionable question for an
  investigator (empty string unless relationship is conflicts)
No prose outside the JSON, no markdown fences."""


def _candidate_pairs(timeline_events: list):
    """Cheap heuristic: group by shared topic keyword, pair across different sources."""
    relevant = [
        e for e in timeline_events
        if any(k in e["description"].lower() for k in TOPIC_KEYWORDS)
    ]
    by_source = {}
    for e in relevant:
        by_source.setdefault(e["source_evidence_id"], []).append(e)

    representatives = []
    for sid, events in by_source.items():
        non_closed = [e for e in events if "closed" not in e["description"].lower()]
        candidates = non_closed if non_closed else events
        candidates.sort(key=lambda e: e["time"] or "")
        representatives.append(candidates[0])

    pairs = []
    for i, a in enumerate(representatives):
        for b in representatives[i + 1 :]:
            pairs.append((a, b))
    return pairs


def _shared_entity_context(case_id: str, a: dict, b: dict) -> str:
    """Checks Stage 11's entity_mentions table for whether both claims'
    source evidence already resolved to the same canonical entity. Returns
    a context string for the debate agents, or empty string if Stage 11
    hasn't run yet / no shared entity found (debate still works without it,
    just with one less grounding fact)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT e.canonical_name, em.observation_id
           FROM entity_mentions em JOIN entities e ON em.entity_id = e.entity_id
           WHERE em.case_id=?""",
        (case_id,),
    )
    rows = cur.fetchall()
    conn.close()

    obs_to_entity = {r["observation_id"]: r["canonical_name"] for r in rows}
    entity_a = obs_to_entity.get(a.get("source_observation_id"))
    entity_b = obs_to_entity.get(b.get("source_observation_id"))

    if entity_a and entity_a == entity_b:
        return f"ENTITY-RESOLUTION CONTEXT: both claims have already been independently resolved to the same canonical entity/location: \"{entity_a}\". Treat this as an established fact."
    return ""


def _debate_adjudicate(a: dict, b: dict, entity_context: str, live: bool = False):
    """Runs the 3-agent debate for one candidate pair. Returns
    (providers_used_set, verdict_dict, transcript_dict) — transcript carries
    every agent's full text, not just the final verdict, so the debate is
    inspectable, not a black box.

    live=True prints each agent's full statement to stdout the instant it
    completes (per-call live printing — not token-level streaming, see
    module docstring for that tradeoff)."""
    providers_used = set()

    claims_text = (
        f"Claim A (source: {a['source_evidence_id']}, time: {a['time']}): {a['description']}\n\n"
        f"Claim B (source: {b['source_evidence_id']}, time: {b['time']}): {b['description']}"
    )
    if entity_context:
        claims_text += f"\n\n{entity_context}"

    if live:
        print(f"\n  {'─'*70}")
        print(f"  DEBATE: {a['description'][:60]}  vs  {b['description'][:60]}")
        print(f"  {'─'*70}")
        if entity_context:
            print(f"  [entity context] {entity_context}")

    if live:
        print("  [Prosecutor is arguing...]", end=" ", flush=True)
    provider, prosecutor_result = chat_json(PROSECUTOR_SYSTEM_PROMPT, claims_text, max_tokens=600)
    providers_used.add(provider)
    if live:
        print(f"({provider})")
        print(f"  PROSECUTOR: {prosecutor_result.get('argument', '')}")
    time.sleep(2)

    defender_prompt = f"{claims_text}\n\nProsecutor's argument (for your review, to counter if you can): {prosecutor_result.get('argument', '')}"
    if live:
        print("  [Defender is arguing...]", end=" ", flush=True)
    provider, defender_result = chat_json(DEFENDER_SYSTEM_PROMPT, defender_prompt, max_tokens=600)
    providers_used.add(provider)
    if live:
        print(f"({provider})")
        print(f"  DEFENDER: {defender_result.get('argument', '')}")
    time.sleep(2)

    judge_prompt = (
        f"{claims_text}\n\n"
        f"PROSECUTOR'S ARGUMENT (for same event / real conflict): {prosecutor_result.get('argument', '')}\n\n"
        f"DEFENDER'S ARGUMENT (against / different events or no real conflict): {defender_result.get('argument', '')}\n\n"
        f"Proposed verification question from Prosecutor (use/refine if ruling for conflict): {prosecutor_result.get('proposed_verification_question', '')}"
    )
    if live:
        print("  [Judge is deliberating...]", end=" ", flush=True)
    provider, verdict = chat_json(JUDGE_SYSTEM_PROMPT, judge_prompt, max_tokens=400)
    providers_used.add(provider)
    if live:
        print(f"({provider})")
        print(f"  JUDGE VERDICT: {verdict.get('relationship', '').upper()}")
        print(f"  JUDGE REASON: {verdict.get('reason', '')}")
        if verdict.get("verification_question"):
            print(f"  VERIFICATION QUESTION: {verdict.get('verification_question', '')}")
        print(f"  {'─'*70}\n")
    time.sleep(2)

    transcript = {
        "claims": claims_text,
        "entity_context": entity_context,
        "prosecutor_argument": prosecutor_result.get("argument", ""),
        "prosecutor_proposed_question": prosecutor_result.get("proposed_verification_question", ""),
        "defender_argument": defender_result.get("argument", ""),
        "judge_relationship": verdict.get("relationship", ""),
        "judge_reason": verdict.get("reason", ""),
        "judge_verification_question": verdict.get("verification_question", ""),
    }

    return providers_used, verdict, transcript


def detect_discrepancies(case_id: str, timeline_events: list, live: bool = False):
    conn = get_conn()
    cur = conn.cursor()
    # Same idempotency fix as observe.py/timeline.py: clear this case's
    # prior conflicts/evidence_links so a re-run doesn't pile duplicate
    # debate verdicts (including stale review_status) on top of old ones.
    # Note: this also means re-running the pipeline silently discards any
    # investigator review (confirmed/resolved) on existing conflicts — fine
    # for a pilot where re-running means "redo the analysis from scratch",
    # worth a UI confirmation prompt if that assumption changes later.
    cur.execute("DELETE FROM conflicts WHERE case_id=?", (case_id,))
    cur.execute("DELETE FROM evidence_links WHERE case_id=?", (case_id,))
    cur.execute("DELETE FROM conflict_reviews WHERE case_id=?", (case_id,))

    conflicts = []
    evidence_links = []
    all_providers_used = set()

    for a, b in _candidate_pairs(timeline_events):
        entity_context = _shared_entity_context(case_id, a, b)

        try:
            providers_used, verdict, transcript = _debate_adjudicate(a, b, entity_context, live=live)
        except LLMUnavailableError as e:
            conn.close()
            raise LLMUnavailableError(
                f"Discrepancy debate adjudication failed: {e}\n"
                f"Set at least one of META_API_KEY / GROQ_API_KEY / GOOGLE_API_KEY"
            ) from e

        all_providers_used |= providers_used
        relationship = verdict.get("relationship", "unrelated")

        transcript_json = json.dumps(transcript)

        if relationship == "conflicts":
            conflict_id = f"CFL-{uuid.uuid4().hex[:8]}"
            cur.execute(
                "INSERT INTO conflicts "
                "(conflict_id, case_id, claim_a, source_a, time_a, claim_b, source_b, time_b, "
                "question, nature_of_conflict, transcript, review_status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    conflict_id, case_id,
                    a["description"], a["source_evidence_id"], a["time"],
                    b["description"], b["source_evidence_id"], b["time"],
                    verdict.get("verification_question", ""),
                    verdict.get("reason", ""),
                    transcript_json,
                    "unresolved",
                ),
            )
            conflicts.append(
                {
                    "conflict_id": conflict_id,
                    "claim_a": a["description"], "source_a": a["source_evidence_id"], "time_a": a["time"],
                    "claim_b": b["description"], "source_b": b["source_evidence_id"], "time_b": b["time"],
                    "nature_of_conflict": verdict.get("reason", ""),
                    "question": verdict.get("verification_question", ""),
                    "transcript": transcript,
                    "review_status": "unresolved",
                }
            )
        elif relationship in ("supports", "related_to"):
            link_id = f"LNK-{uuid.uuid4().hex[:8]}"
            cur.execute(
                "INSERT INTO evidence_links VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    link_id, case_id,
                    a["description"], a["source_evidence_id"],
                    b["description"], b["source_evidence_id"],
                    relationship, verdict.get("reason", ""),
                    transcript_json,
                ),
            )
            evidence_links.append(
                {
                    "link_id": link_id,
                    "claim_a": a["description"], "source_a": a["source_evidence_id"],
                    "claim_b": b["description"], "source_b": b["source_evidence_id"],
                    "link_type": relationship, "reason": verdict.get("reason", ""),
                    "transcript": transcript,
                }
            )

    conn.commit()
    append_audit_event(conn, case_id, "system", f"discrepancy_debate_run_via_{all_providers_used}", case_id)
    conn.close()
    return conflicts, evidence_links


def update_review_status(case_id: str, conflict_id: str, status: str, reason: str, actor_username: str, actor_role: str):
    """Investigator-driven only — the debate never sets this, it only
    decides whether a conflict exists at all. A reason is required so every
    status change has a recorded justification, not just a silent flip."""
    if status not in ("confirmed", "resolved", "unresolved"):
        raise ValueError(f"invalid review_status: {status}")
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("a reason is required when changing a conflict's review status")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM conflicts WHERE conflict_id=? AND case_id=?", (conflict_id, case_id))
    if not cur.fetchone():
        conn.close()
        raise ValueError(f"conflict not found: {conflict_id}")

    import datetime

    review_id = f"REV-{uuid.uuid4().hex[:8]}"
    cur.execute(
        "INSERT INTO conflict_reviews VALUES (?,?,?,?,?,?,?,?)",
        (review_id, case_id, conflict_id, status, reason, actor_username, actor_role,
         datetime.datetime.utcnow().isoformat(timespec="seconds")),
    )
    cur.execute(
        "UPDATE conflicts SET review_status=? WHERE conflict_id=? AND case_id=?",
        (status, conflict_id, case_id),
    )
    conn.commit()
    append_audit_event(conn, case_id, actor_role, f"conflict_marked_{status}", conflict_id)
    conn.close()


def get_conflict_reviews(case_id: str, conflict_id: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM conflict_reviews WHERE case_id=? AND conflict_id=? ORDER BY timestamp ASC",
        (case_id, conflict_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
