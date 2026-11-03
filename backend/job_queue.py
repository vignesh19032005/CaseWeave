"""
Stage 20 (second half) — async job queue. Moves the LLM-heavy pipeline work
(Stages 2-10) off the request thread: /process now enqueues a job and
returns immediately with a job_id; a separate `rq worker` process does the
actual work; the client polls /cases/{id}/process/status/{job_id} for
progress/result.

Safety notes:
- Jobs are serialized as JSON, never pickle. A job description read from Redis can therefore never make
  the worker execute arbitrary objects, even if someone can write to Redis.
- Redis may require a password (REDIS_PASSWORD).
- Only one processing job per case may be queued or running at a time (a Redis key with a time limit), so two
  runs cannot delete each other's rows halfway through.
- A job belongs to the case it was started for; asking for its status through another case's URL finds nothing.
"""
import json
import logging
import tempfile
from pathlib import Path

import redis
from rq import Queue
from rq.job import Job
from rq.serializers import JSONSerializer

from secrets_store import get_secret

logger = logging.getLogger("caseweave.jobs")

QUEUE_NAME = "caseweave-process"
JOB_TIMEOUT_S = 3600
CASE_LOCK_TTL_S = JOB_TIMEOUT_S + 600
REPORT_DATA_DIR = Path(__file__).parent / "report_data"


class CaseBusy(RuntimeError):
    """Another processing job for this case is already queued or running."""


def get_redis_connection():
    host = get_secret("REDIS_HOST") or "127.0.0.1"
    port = int(get_secret("REDIS_PORT") or 6381)
    password = get_secret("REDIS_PASSWORD") or None
    return redis.Redis(host=host, port=port, password=password)


def get_queue() -> Queue:
    return Queue(QUEUE_NAME, connection=get_redis_connection(), serializer=JSONSerializer)


def _lock_key(case_id: str) -> str:
    return f"cw:case-job:{case_id}"


def enqueue_process(case_id: str, legal_query: str | None) -> str:
    """Queues a processing job for the case and returns its id. Raises CaseBusy if one is already active."""
    conn = get_redis_connection()
    if not conn.set(_lock_key(case_id), "pending", nx=True, ex=CASE_LOCK_TTL_S):
        raise CaseBusy("This case is already being processed. Wait for it to finish.")
    try:
        job = get_queue().enqueue(run_process_job, case_id, legal_query, job_timeout=JOB_TIMEOUT_S, meta={"case_id": case_id},
                                  result_ttl=86400, failure_ttl=86400)
        conn.set(_lock_key(case_id), job.id, xx=True, ex=CASE_LOCK_TTL_S)
        return job.id
    except Exception:
        conn.delete(_lock_key(case_id))
        raise


def active_job_for_case(case_id: str) -> str | None:
    value = get_redis_connection().get(_lock_key(case_id))
    return value.decode() if value else None


def release_case(case_id: str) -> None:
    try:
        get_redis_connection().delete(_lock_key(case_id))
    except Exception:  # noqa: BLE001 - the key expires on its own
        pass


def get_job_status(job_id: str, case_id: str) -> dict:
    conn = get_redis_connection()
    try:
        job = Job.fetch(job_id, connection=conn, serializer=JSONSerializer)
    except Exception:  # noqa: BLE001 - unknown or expired
        return {"status": "not_found"}
    if (job.meta or {}).get("case_id") != case_id:
        return {"status": "not_found"}  # a job id from another case is not revealed

    result = {"job_id": job_id, "status": job.get_status()}
    if job.is_finished:
        result["result"] = job.result
    elif job.is_failed:
        # the full traceback stays on the server; the user gets the reason in one line
        logger.error("job %s failed: %s", job_id, (job.exc_info or "")[-2000:])
        last = (job.exc_info or "").strip().splitlines()[-1:] or ["unknown error"]
        result["error"] = last[0][:300]
    return result


def _save_report_data(case_id: str, scenarios, legal_results, reconstruction) -> None:
    """What the report needs that is not stored in the database, so a report can be rebuilt later (for example
    after a reviewer confirms a conflict) without calling any model again."""
    REPORT_DATA_DIR.mkdir(exist_ok=True)
    (REPORT_DATA_DIR / f"{case_id}.json").write_text(
        json.dumps({"scenarios": scenarios, "legal_results": legal_results, "reconstruction": reconstruction}, default=str), encoding="utf-8")


def run_process_job(case_id: str, legal_query: str | None):
    """
    The actual pipeline work, moved here from api.py so the RQ worker
    process can import and execute it by reference (RQ serializes jobs as
    a module path + args, not a closure — the function needs to live in an
    importable module, not be defined inline inside a FastAPI route).
    """
    try:
        return _run_process_job(case_id, legal_query)
    finally:
        release_case(case_id)


def _run_process_job(case_id: str, legal_query: str | None):
    from db import get_conn, append_audit_event
    from storage import require_intact, IntegrityError
    from pipeline.observe import run_observation_engine
    from pipeline.timeline import build_timeline
    from pipeline.discrepancy import detect_discrepancies
    from pipeline.legal import search_legal_corpus
    from pipeline.scenarios import generate_scenarios
    from pipeline.case_chat import index_case_evidence
    from pipeline.entities import resolve_entities
    from pipeline.incident_reconstruction import reconstruct_incident
    from pipeline.report_refresh import refresh_reports
    from pipeline.extract import evidence_to_text
    import backup as backup_module
    import shutil

    with get_conn() as conn:
        case = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
        if not case:
            raise ValueError(f"case not found: {case_id}")
        rows = conn.execute("SELECT * FROM evidence_items WHERE case_id=?", (case_id,)).fetchall()

    # Stage 1: turn every evidence file (text, logs, PDFs, image OCR, audio,
    # video) into text for the observation engine. A file that fails to
    # extract is skipped and audited, not allowed to fail the whole run.
    # A file whose bytes no longer match the hash recorded at upload is NOT processed at all.
    evidence_items = []
    extraction_report = []
    work_root = Path(tempfile.mkdtemp(prefix=f"cw_extract_{case_id}_"))
    for r in rows:
        try:
            path = require_intact(case_id, r["evidence_id"], r["filename"], r["file_hash"])
            text, method = evidence_to_text(path, r["evidence_type"], work_root)
        except IntegrityError as e:
            text, method = None, "integrity_failure"
            logger.error("evidence integrity failure in %s: %s", case_id, e)
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the run
            text, method = None, f"failed: {str(e)[:200]}"
        extraction_report.append({"evidence_id": r["evidence_id"], "filename": r["filename"], "method": method,
                                  "extracted": text is not None})
        if text is None:
            continue
        evidence_items.append({"evidence_id": r["evidence_id"], "path": path,
                               "evidence_type": r["evidence_type"], "content": text})

    shutil.rmtree(work_root, ignore_errors=True)  # extracted frames/audio are intermediates, not evidence

    with get_conn() as log_conn:
        for rep in extraction_report:
            action = f"extracted_{rep['method']}" if rep["extracted"] else f"extraction_skipped_{rep['method']}"
            append_audit_event(log_conn, case_id, "system", action[:128], rep["evidence_id"])

    if not evidence_items:
        raise ValueError("no evidence with extractable content yet")

    # Mid-run checkpointing: resumes any previously extracted observations if a prior
    # job was terminated/restarted mid-pipeline, avoiding redundant LLM costs
    observations = run_observation_engine(case_id, evidence_items, resume_checkpoint=True)
    timeline_events = build_timeline(case_id)

    # Entity resolution runs before discrepancy detection so its output
    # grounds the debate agents with an established "same canonical
    # entity" fact — same ordering as the CLI run_pipeline.py.
    entity_result = resolve_entities(case_id)
    conflicts, evidence_links = detect_discrepancies(case_id, timeline_events)
    scenarios = generate_scenarios(conflicts, case_id=case_id)
    legal_results = search_legal_corpus(legal_query) if legal_query else []
    index_case_evidence(case_id)

    try:
        reconstruction = reconstruct_incident(
            case_id, timeline_events, entity_result["entities"], entity_result["relationships"],
            conflicts, evidence_links,
        )
    except Exception:  # noqa: BLE001 - Stage 9a is additive, not required for a usable report
        logger.exception("incident reconstruction failed for %s", case_id)
        reconstruction = None

    _save_report_data(case_id, scenarios, legal_results, reconstruction)
    paths = refresh_reports(case_id)

    try:
        summary = backup_module.run_backup()
        if summary.get("errors"):
            logger.error("backup finished with errors: %s", summary["errors"])
    except Exception:  # noqa: BLE001 - a backup failure must not fail processing, but it must not be silent either
        logger.exception("backup failed after processing %s", case_id)

    return {
        "observations_count": len(observations),
        "extraction": extraction_report,
        "timeline_events": timeline_events,
        "entities": entity_result["entities"],
        "relationships": entity_result["relationships"],
        "conflicts": conflicts,
        "evidence_links": evidence_links,
        "scenarios": scenarios,
        "legal_results": legal_results,
        "reconstruction": reconstruction,
        "report_path": paths["markdown"],
        "pdf_report_path": paths["pdf"],
        "timeline_html_path": paths["timeline_html"],
    }
