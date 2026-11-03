"""
Stage 2 — Observation Engine. Calls the real LLM (Meta -> local -> Groq -> Gemini
fallback chain, see llm_client.py). No mock mode: if no provider can answer, this stage raises
LLMUnavailableError rather than faking output.

Robustness (all of it exists because real model output is not always well-formed):
- long documents are split into chunks so the reply is never cut off mid-JSON;
- each reply is read through llm_schema, so a missing field, a wrong type or an unknown label cannot crash the
  run or store garbage; times are normalised to 24-hour HH:MM[:SS] or dropped;
- a reply that is not JSON is retried once; a file whose reply is still unusable is skipped and audited, and
  the rest of the case carries on;
- identifiers are redacted before the text is sent (see llm_guard), and instruction-like text inside evidence
  is removed and recorded (see evidence_guard).
"""
import json
import os
import re
import time
import uuid
from pathlib import Path

from db import get_conn, append_audit_event
from llm_client import LLMUnavailableError
from logging_config import get_logger, log_event
from pipeline import llm_schema as sch
from pipeline.evidence_guard import screen_text
from pipeline.llm_guard import case_redactor, safe_chat_json
from pipeline.timeutil import normalize_clock

_log = get_logger("pipeline.observe")

CHUNK_CHARS = 7000
CLASSIFICATIONS = ("observed", "reported", "inferred", "disputed", "unknown")

SYSTEM_PROMPT = """You are an evidence observation extractor for CaseWeave, an
investigation support tool. You are given one piece of evidence text. Extract
every distinct factual claim as a separate observation. For each one, output:
- description: the claim, close to the source wording
- classification: one of observed | reported | inferred | disputed | unknown
  (observed = directly recorded by a device/camera/sensor; reported = a
  person's stated claim; inferred = someone's interpretation/synthesis of
  other evidence; unknown = the evidence explicitly says something is not
  established)
- extracted_time: a time in 24-hour HH:MM format if the claim states or
  implies one, else null. Markers like "[+00:12 elapsed]" in transcripts or
  video frames are offsets from the start of a recording, NOT clock times —
  never put them in extracted_time (mention them in limitations instead)
- limitations: a list of short strings noting any stated uncertainty (e.g.
  "clock sync unverified", "witness expressed uncertainty"), else []
- subject: the primary named person, device, or entity the claim is about
  (e.g. "R. Kumaran", "ACC-DOOR-02", "CAM-02"), else null
- action: the verb/action phrase (e.g. "entered", "door opened", "checked
  phone"), else null
- location: the place named or implied (e.g. "side entrance", "Ganga
  Street"), else null
- time_claim: the raw time phrase as originally stated, before your
  normalization (e.g. "around 9:10 PM, maybe a few minutes before or
  after"), else null

Respond with ONLY a JSON array of objects with exactly these eight keys. No
prose, no markdown fences, no commentary."""


def split_chunks(content: str, limit: int = CHUNK_CHARS) -> list:
    """Splits on line boundaries into pieces of at most `limit` characters (a single longer line is cut)."""
    if len(content) <= limit:
        return [content]
    chunks, current, size = [], [], 0
    for line in content.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append("".join(current))
                current, size = [], 0
            chunks.append(line[:limit])
            line = line[limit:]
        if size + len(line) > limit and current:
            chunks.append("".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def clean_observation(item: dict) -> dict | None:
    """One model-proposed observation as a safe record, or None if it has no description."""
    description = sch.text(item.get("description"), 2000)
    if not description:
        return None
    raw_time = item.get("extracted_time")
    extracted = normalize_clock(raw_time)
    limitations = sch.string_list(item.get("limitations"))
    if raw_time and not extracted and not re.fullmatch(r"\s*(null|none|n/?a|unknown)?\s*", str(raw_time), re.I):
        limitations.append(f"the model gave a time that could not be read as a clock time: {str(raw_time)[:40]}")
    return {
        "description": description,
        "classification": sch.choice(item.get("classification"), CLASSIFICATIONS, "unknown"),
        "extracted_time": extracted,
        "limitations": limitations,
        "subject": sch.text(item.get("subject"), 300),
        "action": sch.text(item.get("action"), 300),
        "location": sch.text(item.get("location"), 300),
        "time_claim": sch.text(item.get("time_claim"), 300),
    }


def extract_observations_from_source(evidence_id: str, filename: str, evidence_type: str, content: str, case_id: str | None = None, redactor=None):
    redactor = redactor or case_redactor(case_id)
    observations, guard_hits = [], 0
    for chunk_no, chunk in enumerate(split_chunks(content)):
        safe_text, found = screen_text(chunk)
        guard_hits += len(found)
        prompt = f"Evidence file: {filename}\nEvidence type: {evidence_type}\n\nContent:\n{safe_text}"
        last_error = None
        for _attempt in range(2):
            try:
                provider, items = safe_chat_json(case_id, SYSTEM_PROMPT, prompt, max_tokens=3072, redactor=redactor)
                break
            except LLMUnavailableError as e:
                last_error = e
                if "non-JSON" not in str(e):
                    raise  # providers are down: stop and let the caller report it
        else:
            raise ValueError(f"unusable model output for {filename} (part {chunk_no + 1}): {str(last_error)[:160]}")
        for item in sch.records(items):
            clean = clean_observation(item)
            if not clean:
                continue
            idx = len(observations)
            observations.append({
                "observation_id": f"OBS-{uuid.uuid4().hex[:8]}",
                **clean,
                "source_evidence_id": evidence_id,
                "source_locator": f"{filename}#item_{idx}",
                "llm_provider": provider,
            })
    if guard_hits:
        log_event(_log, "warning", "instruction-like text removed from evidence", evidence_id=evidence_id, removed=guard_hits)
    return observations


def run_observation_engine(case_id: str, evidence_items: list, resume_checkpoint: bool = True):
    conn = get_conn()
    cur = conn.cursor()
    redactor = case_redactor(case_id)
    pacing = float(os.environ.get("LLM_CALL_PACING_S", "1"))

    # Mid-run checkpointing:
    # If resuming from checkpoint, check which evidence items already have observations
    # persisted in the database. This saves valuable tokens and avoids redundant LLM
    # calls if a previous run was interrupted or crashed.
    cur.execute("SELECT DISTINCT source_evidence_id FROM observations WHERE case_id=?", (case_id,))
    completed_evidence_ids = {r["source_evidence_id"] for r in cur.fetchall()}

    if not resume_checkpoint or not completed_evidence_ids:
        cur.execute("DELETE FROM observations WHERE case_id=?", (case_id,))
        completed_evidence_ids = set()

    all_observations = []
    # If resuming, load previously extracted observations for this case
    if completed_evidence_ids:
        cur.execute("SELECT * FROM observations WHERE case_id=?", (case_id,))
        for r in cur.fetchall():
            all_observations.append({
                "observation_id": r["observation_id"],
                "description": r["description"],
                "classification": r["classification"],
                "source_evidence_id": r["source_evidence_id"],
                "source_locator": r["source_locator"],
                "extracted_time": r["extracted_time"],
                "limitations": json.loads(r["limitations"]) if isinstance(r["limitations"], str) else (r["limitations"] or []),
                "subject": r["subject"],
                "action": r["action"],
                "location": r["location"],
                "time_claim": r["time_claim"],
                "llm_provider": "checkpoint",
            })

    providers_used = set()

    for item in evidence_items:
        evidence_id = item["evidence_id"]
        path: Path = item["path"]

        # Checkpoint hit: skip LLM call if this exhibit was already processed
        if resume_checkpoint and evidence_id in completed_evidence_ids:
            continue

        # Media evidence (PDF/audio/video/image) arrives pre-extracted by
        # Stage 1 (pipeline/extract.evidence_to_text); plain text is read here.
        content = item.get("content")
        if content is None:
            content = path.read_text(encoding="utf-8", errors="replace")

        try:
            obs = extract_observations_from_source(evidence_id, path.name, item["evidence_type"], content, case_id=case_id, redactor=redactor)
        except LLMUnavailableError as e:
            conn.close()
            raise LLMUnavailableError(
                f"Observation extraction failed for {path.name}: {e}\n"
                f"Set at least one of META_API_KEY / GROQ_API_KEY / GOOGLE_API_KEY in backend/.env"
            ) from e
        except ValueError as e:
            # the model's reply for this file was unusable twice: skip the file, say so in the audit trail, carry on
            log_event(_log, "error", "observation extraction skipped a file", evidence_id=evidence_id, reason=str(e)[:200])
            append_audit_event(conn, case_id, "system", "observations_skipped_unusable_model_output", evidence_id)
            continue

        for o in obs:
            providers_used.add(o["llm_provider"])
            cur.execute(
                "INSERT INTO observations (observation_id, case_id, description, classification, source_evidence_id, source_locator, "
                "extracted_time, limitations, subject, action, location, time_claim) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    o["observation_id"], case_id, o["description"], o["classification"], o["source_evidence_id"], o["source_locator"],
                    o["extracted_time"], json.dumps(o["limitations"]), o["subject"], o["action"], o["location"], o["time_claim"],
                ),
            )
        conn.commit()
        append_audit_event(conn, case_id, "system", f"observations_extracted_via_{obs[0]['llm_provider'] if obs else 'none'}", evidence_id)
        all_observations.extend(obs)
        if pacing:
            time.sleep(pacing)  # stay under free-tier tokens-per-minute limits between sequential calls

    conn.close()
    if providers_used - {"meta"}:
        log_event(_log, "warning", "non-primary providers used in Stage 2", providers=list(providers_used))
    return all_observations
