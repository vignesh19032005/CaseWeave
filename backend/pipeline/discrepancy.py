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

Which pairs get debated (the part that decides what the tool can find):
every timed claim is placed in the topic groups it belongs to (entry/alarm, movement, loot, vehicle, person
description, and the non-burglary groups: signals, speed, collision or injury, emergency calls, access control). Claims from DIFFERENT sources that share a group and fall within 90 minutes of each other are
scored by how similar their wording is (sentence embeddings, with a word-overlap fallback) and how close in
time they are, and the best MAX_PAIRS pairs are debated. An earlier version debated only the earliest door
event of each source, so a forced-entry alarm was compared with an unrelated line of the CCTV log and the real
discrepancy between them was never examined.

Known design assumption: the rubric below leans towards "same event, timing discrepancy" when two sources
describe the same kind of event at the same place. That is deliberate (a missed discrepancy costs more than a
flagged one that a reviewer dismisses) but it means the tool errs towards flagging; every flag goes to a
human reviewer with the full debate transcript.

Entity-resolution grounding (Stage 11, run BEFORE Stage 4): if both claims already resolve to the same
canonical entity/location, that's handed to all three agents as an established fact.
"""
import itertools
import json
import os
import re
import sys
import time
import uuid

from db import get_conn, append_audit_event, utcnow
from llm_client import LLMUnavailableError
from pipeline import llm_schema as sch
from pipeline.llm_guard import case_redactor, safe_chat_json
from pipeline.timeutil import parse_seconds

MAX_PAIRS = 8
WINDOW_MIN = 90
MIN_SCORE = 0.30
MAX_USES_PER_EVENT = 2
UNTIMED_LABEL = "no time stated"
MAX_UNTIMED_PAIRS = 6        # extra pairs: a statement that gives no time, against a recorded event of another source on the same topic
MIN_UNTIMED_SCORE = 0.42

def _words(*stems: str) -> "re.Pattern":
    """Whole words only: each stem may carry an ordinary ending (s, es, ed, d, ing), nothing else. This is what stops
    'entertainment' counting as 'enter' and 'disclosed' as 'closed'."""
    return re.compile(r"\b(?:" + "|".join(stems) + r")(?:s|es|ed|d|ing)?\b", re.I)


TOPIC_GROUPS = {
    "entry": _words("door", "gate", "shutter", "window", "lock", "enter", "entry", "entries", "entrance", "open", "inside", "breach", "force", "forc",
                    "pry", "pri", "prise", "tamper", "alarm", "sensor", "camera", "overlay", "lift", "lifted"),
    "movement": _words("flee", "fled", "run", "ran", "walk", "jog", "leave", "left", "arrive", "arrival", "depart", "exit", "approach", "emerge", "escape"),
    "loot": _words("cash", "rs", "inr", "rupee", "stolen", "stole", "theft", "missing", "duffel", "bag", "drawer", "cabinet", "vault", "narcotic", "drug"),
    "vehicle": _words("car", "bike", "motorcycle", "scooter", "van", "truck", "vehicle", "auto", "lorry"),
    "person": _words("wear", "wearing", "jacket", "hood", "shirt", "glove", "male", "female", "height", "tall", "build", "mask", "shoe", "beard"),
    # Topics that are not about a break-in, so the same detector finds disagreements in a collision or an assault as well.
    "signal": _words("light", "signal", "green", "red", "amber", "phase", "stop line"),
    "speed": _words("speed", "kmh", "mph", "brak", "brake", "accelerat", "slow", "fast", "faster"),
    "collision": _words("collision", "collid", "impact", "struck", "strike", "hit", "crash", "fall", "fell", "slid", "injur", "bleed", "blow", "push",
                        "shov", "thud", "thump", "assault", "punch", "attack", "wound", "laceration"),
    "emergency": _words("call", "ambulance", "dispatch", "emergency", "police", "responder", "paramedic", "hospital"),
    "access": _words("card", "reader", "granted", "keypad", "badge", "access", "unlock", "arm", "disarm"),
}
_NEGATED_CLOSED = re.compile(r"\bclosed\b", re.I)

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
  not merely because reconciling them requires judgment.
- If the evidence documents a known clock offset between the two sources (for example a camera clock that runs
  fast), say so: a difference fully explained by that offset is "supports", not a conflict."""

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

RELATIONSHIPS = ("conflicts", "supports", "related_to", "unrelated")


# ------------------------------------------------------------- choosing pairs ----

def event_groups(description: str) -> set:
    desc = (description or "").replace("_", " ")  # device logs write door_opened, rear_shutter_gate_b
    groups = {name for name, rx in TOPIC_GROUPS.items() if rx.search(desc)}
    if "entry" in groups and _NEGATED_CLOSED.search(desc) and len(groups) == 1:
        groups.discard("entry")  # "door closed" alone is not an entry event
    return groups


def _gap_minutes(a: str, b: str):
    sa, sb = parse_seconds(a), parse_seconds(b)
    if sa is None or sb is None:
        return None
    d = abs(sa - sb)
    return min(d, 86400 - d) / 60.0


def _word_overlap(a: str, b: str) -> float:
    wa, wb = set(re.findall(r"[a-z0-9]{3,}", a.lower())), set(re.findall(r"[a-z0-9]{3,}", b.lower()))
    return len(wa & wb) / max(1, len(wa | wb))


def _similarities(texts: list):
    """Cosine similarity matrix of the texts using the sentence-embedding model, or None if it is unavailable."""
    try:
        from pipeline.legal import _get_model
        vecs = _get_model().encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return vecs @ vecs.T
    except Exception:  # noqa: BLE001 - the word-overlap fallback below still finds pairs
        return None


def _candidate_pairs(timeline_events: list, max_pairs: int = MAX_PAIRS):
    """The pairs of claims worth debating, best first."""
    events = [e for e in timeline_events if e.get("time") and parse_seconds(e["time"]) is not None and e.get("description")]
    grouped = [(i, e, event_groups(e["description"])) for i, e in enumerate(events)]
    grouped = [g for g in grouped if g[2]]
    if len(grouped) < 2:
        return []
    sims = _similarities([e["description"] for _, e, _ in grouped])
    scored = []
    pos = {g[0]: k for k, g in enumerate(grouped)}
    for (ia, a, ga), (ib, b, gb) in itertools.combinations(grouped, 2):
        if a["source_evidence_id"] == b["source_evidence_id"] or not (ga & gb):
            continue
        gap = _gap_minutes(a["time"], b["time"])
        if gap is None or gap > WINDOW_MIN:
            continue
        ra, rb = pos[ia], pos[ib]
        sim = float(sims[ra][rb]) if sims is not None else _word_overlap(a["description"], b["description"]) * 1.5
        score = sim + 0.10 * (1 - gap / WINDOW_MIN)
        if score >= MIN_SCORE:
            scored.append((score, a, b))
    scored.sort(key=lambda x: -x[0])
    uses, pairs = {}, []
    for _, a, b in scored:
        ka, kb = a.get("event_id") or id(a), b.get("event_id") or id(b)
        if uses.get(ka, 0) >= MAX_USES_PER_EVENT or uses.get(kb, 0) >= MAX_USES_PER_EVENT:
            continue
        uses[ka] = uses.get(ka, 0) + 1
        uses[kb] = uses.get(kb, 0) + 1
        pairs.append((a, b))
        if len(pairs) >= max_pairs:
            break
    return pairs


def _untimed_pairs(case_id: str, timeline_events: list, max_pairs: int = MAX_UNTIMED_PAIRS):
    """Statements often say what happened without saying when ("the lights were green for me"). They never reach the timeline, so they could
    not be compared with a recorded event ("signal log: red"). Here each such reported claim is paired with the best-matching recorded event of
    another source that shares its topic; the same debate then decides. Few pairs, strict score, and the claim is shown as having no time."""
    try:
        with get_conn() as conn:
            rows = conn.execute("SELECT observation_id, source_evidence_id, description FROM observations WHERE case_id=? AND extracted_time IS NULL AND classification='reported'",
                                (case_id,)).fetchall()
    except Exception:  # noqa: BLE001 - an extra pass must never stop the main one
        return []
    claims = [{"event_id": r["observation_id"], "time": UNTIMED_LABEL, "description": r["description"], "source_observation_id": r["observation_id"],
               "source_evidence_id": r["source_evidence_id"], "classification": "reported"} for r in rows if len(r["description"] or "") >= 25]
    recorded = [e for e in timeline_events if e.get("classification") == "observed" and e.get("description")]
    if not claims or not recorded:
        return []
    texts = [c["description"] for c in claims] + [e["description"] for e in recorded]
    sims = _similarities(texts)
    scored = []
    for i, c in enumerate(claims):
        gc = event_groups(c["description"])
        for j, e in enumerate(recorded):
            shared = (gc & event_groups(e["description"])) - {"person", "vehicle"}     # a shared description of a person or a vehicle is identity, not a claim about what happened
            if not shared or c["source_evidence_id"] == e["source_evidence_id"]:
                continue
            sim = float(sims[i][len(claims) + j]) if sims is not None else _word_overlap(c["description"], e["description"]) * 1.5
            score = sim + 0.10 * len(shared)
            if score >= MIN_UNTIMED_SCORE:
                scored.append((score, c, e))
    # One pair per statement and recorded source: the statement against the few entries of that source that match it best, shown together, so the
    # debate sees the whole stretch of the record (for example every phase of a signal log) and not a single line picked by similarity.
    by_claim: dict = {}
    for score, c, e in scored:
        by_claim.setdefault(c["event_id"], {"claim": c, "sources": {}})["sources"].setdefault(e["source_evidence_id"], []).append((score, e))
    ranked = []
    for entry in by_claim.values():
        srcs = sorted(entry["sources"].items(), key=lambda kv: -max(sc for sc, _ in kv[1]))[:2]     # the two best-matching sources for this statement
        for src, evs in srcs:
            evs.sort(key=lambda x: -x[0])
            top = sorted((e for _, e in evs[:5]), key=lambda e: e["time"])          # up to five matching entries, in time order
            bundle = {"event_id": top[0].get("event_id"), "time": top[0]["time"], "source_evidence_id": src, "classification": "observed",
                      "source_observation_id": top[0].get("source_observation_id"),
                      "description": ("Entries from this record: " + "; ".join(e["time"] + " " + e["description"] for e in top)) if len(top) > 1 else top[0]["description"]}
            ranked.append((evs[0][0], entry["claim"], bundle))
    ranked.sort(key=lambda x: -x[0])
    pairs = []
    for _, c, bundle in ranked:
        pairs.append((c, bundle))
        if len(pairs) >= max_pairs:
            break
    return pairs


def _shared_entity_context(entity_by_obs: dict, a: dict, b: dict) -> str:
    """Whether both claims' source observations already resolved to the same canonical entity (Stage 11).
    Returns a context string for the debate agents, or empty string if Stage 11 hasn't run / nothing shared."""
    entity_a = entity_by_obs.get(a.get("source_observation_id"), set())
    entity_b = entity_by_obs.get(b.get("source_observation_id"), set())
    shared = sorted(entity_a & entity_b)
    if shared:
        return (f"ENTITY-RESOLUTION CONTEXT: both claims have already been independently resolved to the same canonical "
                f"entity/location: \"{shared[0]}\". Treat this as an established fact.")
    return ""


def _entity_map(case_id: str) -> dict:
    out: dict = {}
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT e.canonical_name, em.observation_id
               FROM entity_mentions em JOIN entities e ON em.entity_id = e.entity_id
               WHERE em.case_id=?""", (case_id,)).fetchall()
    for r in rows:
        out.setdefault(r["observation_id"], set()).add(r["canonical_name"])
    return out


# ----------------------------------------------------------------- the debate ----

def _safe_print(text: str, **kwargs):
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(text.encode(encoding, errors="replace").decode(encoding), **kwargs)


def _agent(case_id, redactor, system, prompt, max_tokens):
    """One debate turn; a reply that is not JSON is retried once."""
    last = None
    for _ in range(2):
        try:
            provider, result = safe_chat_json(case_id, system, prompt, max_tokens, redactor=redactor)
            return provider, (result if isinstance(result, dict) else {})
        except LLMUnavailableError as e:
            last = e
            if "non-JSON" not in str(e):
                raise
    raise last or LLMUnavailableError("model gave no usable reply")


def _debate_adjudicate(a: dict, b: dict, entity_context: str, live: bool = False, case_id: str | None = None, redactor=None):
    """Runs the 3-agent debate for one candidate pair. Returns
    (providers_used_set, verdict_dict, transcript_dict) — transcript carries
    every agent's full text, not just the final verdict, so the debate is
    inspectable, not a black box."""
    providers_used = set()
    redactor = redactor or case_redactor(case_id)
    pacing = float(os.environ.get("LLM_CALL_PACING_S", "1"))

    claims_text = (
        f"Claim A (source: {a['source_evidence_id']}, time: {a['time']}): {a['description']}\n\n"
        f"Claim B (source: {b['source_evidence_id']}, time: {b['time']}): {b['description']}"
    )
    if entity_context:
        claims_text += f"\n\n{entity_context}"

    if live:
        _safe_print(f"\n  {'-'*70}")
        _safe_print(f"  DEBATE: {a['description'][:60]}  vs  {b['description'][:60]}")
        _safe_print(f"  {'-'*70}")

    provider, prosecutor_result = _agent(case_id, redactor, PROSECUTOR_SYSTEM_PROMPT, claims_text, 600)
    providers_used.add(provider)
    if live:
        _safe_print(f"  PROSECUTOR ({provider}): {sch.text(prosecutor_result.get('argument')) or ''}")
    time.sleep(pacing)

    prosecutor_arg = sch.text(prosecutor_result.get("argument"), 1500) or ""
    defender_prompt = f"{claims_text}\n\nProsecutor's argument (for your review, to counter if you can): {prosecutor_arg}"
    provider, defender_result = _agent(case_id, redactor, DEFENDER_SYSTEM_PROMPT, defender_prompt, 600)
    providers_used.add(provider)
    defender_arg = sch.text(defender_result.get("argument"), 1500) or ""
    if live:
        _safe_print(f"  DEFENDER ({provider}): {defender_arg}")
    time.sleep(pacing)

    prosecutor_q = sch.text(prosecutor_result.get("proposed_verification_question"), 500) or ""
    judge_prompt = (
        f"{claims_text}\n\n"
        f"PROSECUTOR'S ARGUMENT (for same event / real conflict): {prosecutor_arg}\n\n"
        f"DEFENDER'S ARGUMENT (against / different events or no real conflict): {defender_arg}\n\n"
        f"Proposed verification question from Prosecutor (use/refine if ruling for conflict): {prosecutor_q}"
    )
    provider, verdict_raw = _agent(case_id, redactor, JUDGE_SYSTEM_PROMPT, judge_prompt, 400)
    providers_used.add(provider)
    verdict = {
        "relationship": sch.choice(verdict_raw.get("relationship"), RELATIONSHIPS, "unrelated"),
        "reason": sch.text(verdict_raw.get("reason"), 800) or "",
        "verification_question": sch.text(verdict_raw.get("verification_question"), 500) or "",
    }
    if live:
        _safe_print(f"  JUDGE ({provider}): {verdict['relationship'].upper()} - {verdict['reason']}")
    time.sleep(pacing)

    transcript = {
        "claims": claims_text,
        "entity_context": entity_context,
        "prosecutor_argument": prosecutor_arg,
        "prosecutor_proposed_question": prosecutor_q,
        "defender_argument": defender_arg,
        "judge_relationship": verdict["relationship"],
        "judge_reason": verdict["reason"],
        "judge_verification_question": verdict["verification_question"],
    }
    return providers_used, verdict, transcript


def _pair_key(src_a, time_a, src_b, time_b):
    return tuple(sorted([(src_a, time_a), (src_b, time_b)], key=lambda x: (str(x[0]), str(x[1]))))


def detect_discrepancies(case_id: str, timeline_events: list, live: bool = False):
    conn = get_conn()
    cur = conn.cursor()

    # Re-running replaces the debate verdicts, but NOT the investigators' decisions: reviews are kept as history,
    # and a conflict that comes back with the same two claims is given its review status again (with an audit
    # entry), so a re-run never silently reopens something a reviewer already settled.
    cur.execute("SELECT conflict_id, source_a, time_a, source_b, time_b, review_status FROM conflicts WHERE case_id=?", (case_id,))
    previous = {_pair_key(r["source_a"], r["time_a"], r["source_b"], r["time_b"]): r for r in cur.fetchall()}
    cur.execute("DELETE FROM conflicts WHERE case_id=?", (case_id,))
    cur.execute("DELETE FROM evidence_links WHERE case_id=?", (case_id,))

    conflicts = []
    evidence_links = []
    all_providers_used = set()
    redactor = case_redactor(case_id)
    entity_by_obs = _entity_map(case_id)
    carried = 0

    for a, b in _candidate_pairs(timeline_events) + _untimed_pairs(case_id, timeline_events):
        entity_context = _shared_entity_context(entity_by_obs, a, b)

        try:
            providers_used, verdict, transcript = _debate_adjudicate(a, b, entity_context, live=live, case_id=case_id, redactor=redactor)
        except LLMUnavailableError as e:
            conn.rollback()
            conn.close()
            raise LLMUnavailableError(
                f"Discrepancy debate adjudication failed: {e}\n"
                f"Set at least one of META_API_KEY / GROQ_API_KEY / GOOGLE_API_KEY"
            ) from e

        all_providers_used |= providers_used
        relationship = verdict["relationship"]
        transcript_json = json.dumps(transcript)

        if relationship == "conflicts":
            conflict_id = f"CFL-{uuid.uuid4().hex[:8]}"
            old = previous.get(_pair_key(a["source_evidence_id"], a["time"], b["source_evidence_id"], b["time"]))
            status = old["review_status"] if old and old["review_status"] else "unresolved"
            cur.execute(
                "INSERT INTO conflicts "
                "(conflict_id, case_id, claim_a, source_a, time_a, claim_b, source_b, time_b, "
                "question, nature_of_conflict, transcript, review_status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    conflict_id, case_id,
                    a["description"], a["source_evidence_id"], a["time"],
                    b["description"], b["source_evidence_id"], b["time"],
                    verdict["verification_question"], verdict["reason"], transcript_json, status,
                ),
            )
            if old and status != "unresolved":
                cur.execute(
                    "INSERT INTO conflict_reviews (review_id, case_id, conflict_id, status, reason, actor_username, actor_role, timestamp) VALUES (?,?,?,?,?,?,?,?)",
                    (f"REV-{uuid.uuid4().hex[:8]}", case_id, conflict_id, status,
                     f"Carried over from {old['conflict_id']} when the analysis was re-run; the same two claims were found again.",
                     "system", "system", utcnow().isoformat(timespec="seconds")),
                )
                carried += 1
            conflicts.append(
                {
                    "conflict_id": conflict_id,
                    "claim_a": a["description"], "source_a": a["source_evidence_id"], "time_a": a["time"],
                    "claim_b": b["description"], "source_b": b["source_evidence_id"], "time_b": b["time"],
                    "nature_of_conflict": verdict["reason"],
                    "question": verdict["verification_question"],
                    "transcript": transcript,
                    "review_status": status,
                }
            )
        elif relationship in ("supports", "related_to"):
            link_id = f"LNK-{uuid.uuid4().hex[:8]}"
            cur.execute(
                "INSERT INTO evidence_links (link_id, case_id, claim_a, source_a, claim_b, source_b, link_type, reason, transcript) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    link_id, case_id,
                    a["description"], a["source_evidence_id"],
                    b["description"], b["source_evidence_id"],
                    relationship, verdict["reason"], transcript_json,
                ),
            )
            evidence_links.append(
                {
                    "link_id": link_id,
                    "claim_a": a["description"], "source_a": a["source_evidence_id"],
                    "claim_b": b["description"], "source_b": b["source_evidence_id"],
                    "link_type": relationship, "reason": verdict["reason"],
                    "transcript": transcript,
                }
            )

    conn.commit()
    append_audit_event(conn, case_id, "system", f"discrepancy_debate_run_via_{'_'.join(sorted(all_providers_used)) or 'none'}", case_id)
    if carried:
        append_audit_event(conn, case_id, "system", "conflict_reviews_carried_over", f"{carried} review(s)")
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

    review_id = f"REV-{uuid.uuid4().hex[:8]}"
    cur.execute(
        "INSERT INTO conflict_reviews (review_id, case_id, conflict_id, status, reason, actor_username, actor_role, timestamp) VALUES (?,?,?,?,?,?,?,?)",
        (review_id, case_id, conflict_id, status, reason, actor_username, actor_role,
         utcnow().isoformat(timespec="seconds")),
    )
    cur.execute(
        "UPDATE conflicts SET review_status=? WHERE conflict_id=? AND case_id=?",
        (status, conflict_id, case_id),
    )
    conn.commit()
    append_audit_event(conn, case_id, actor_role, f"conflict_marked_{status}", conflict_id, actor_user=actor_username)
    conn.close()


def get_conflict_reviews(case_id: str, conflict_id: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM conflict_reviews WHERE case_id=? AND conflict_id=? ORDER BY timestamp ASC",
        (case_id, conflict_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
