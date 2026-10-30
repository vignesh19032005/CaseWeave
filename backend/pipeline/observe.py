"""
Stage 2 — Observation Engine. Calls the real LLM (Meta -> Groq -> Gemini
fallback chain, see llm_client.py). No mock mode: if no API key is set in
backend/.env, this stage raises LLMUnavailableError rather than faking output.
"""
import json
import re
import time
import uuid
from pathlib import Path

from db import get_conn, append_audit_event
from llm_client import chat_json, LLMUnavailableError
from logging_config import get_logger, log_event

_log = get_logger("pipeline.observe")

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


def extract_observations_from_source(evidence_id: str, filename: str, evidence_type: str, content: str):
    prompt = f"Evidence file: {filename}\nEvidence type: {evidence_type}\n\nContent:\n{content}"
    provider, items = chat_json(SYSTEM_PROMPT, prompt, max_tokens=3072)

    observations = []
    for idx, item in enumerate(items):
        observations.append(
            {
                "observation_id": f"OBS-{uuid.uuid4().hex[:8]}",
                "description": item.get("description", "").strip(),
                "classification": item.get("classification", "unknown"),
                "source_evidence_id": evidence_id,
                "source_locator": f"{filename}#item_{idx}",
                "extracted_time": item.get("extracted_time"),
                "limitations": item.get("limitations", []),
                "subject": item.get("subject"),
                "action": item.get("action"),
                "location": item.get("location"),
                "time_claim": item.get("time_claim"),
                "llm_provider": provider,
            }
        )
    return observations


def run_observation_engine(case_id: str, evidence_items: list):
    conn = get_conn()
    cur = conn.cursor()
    # Make a re-run of /process idempotent instead of accumulating
    # duplicate observations on top of a prior run's output (each
    # observation gets a fresh uuid, so INSERT OR REPLACE never collides
    # with the old rows — they'd otherwise just pile up).
    cur.execute("DELETE FROM observations WHERE case_id=?", (case_id,))
    all_observations = []
    providers_used = set()

    for item in evidence_items:
        path: Path = item["path"]
        evidence_id = item["evidence_id"]

        # Media evidence (PDF/audio/video/image) arrives pre-extracted by
        # Stage 1 (pipeline/extract.evidence_to_text); plain text is read here.
        content = item.get("content")
        if content is None:
            content = path.read_text(encoding="utf-8")

        try:
            obs = extract_observations_from_source(evidence_id, path.name, item["evidence_type"], content)
        except LLMUnavailableError as e:
            conn.close()
            raise LLMUnavailableError(
                f"Observation extraction failed for {path.name}: {e}\n"
                f"Set at least one of META_API_KEY / GROQ_API_KEY / GOOGLE_API_KEY in backend/.env"
            ) from e

        for o in obs:
            providers_used.add(o["llm_provider"])
            cur.execute(
                "INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    o["observation_id"],
                    case_id,
                    o["description"],
                    o["classification"],
                    o["source_evidence_id"],
                    o["source_locator"],
                    o["extracted_time"],
                    json.dumps(o["limitations"]),
                    o["subject"],
                    o["action"],
                    o["location"],
                    o["time_claim"],
                ),
            )
        conn.commit()
        append_audit_event(conn, case_id, "system", f"observations_extracted_via_{obs[0]['llm_provider'] if obs else 'none'}", evidence_id)
        all_observations.extend(obs)
        time.sleep(2)  # stay under free-tier tokens-per-minute limit between sequential calls

    conn.close()
    if providers_used - {"meta"}:
        log_event(_log, "warning", "non-primary providers used in Stage 2", providers=list(providers_used))
    return all_observations
