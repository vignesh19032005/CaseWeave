"""
Stage 20 (second half) — async job queue. Moves the LLM-heavy pipeline work
(Stages 2-10) off the request thread: /process now enqueues a job and
returns immediately with a job_id; a separate `rq worker` process does the
actual work; the client polls /cases/{id}/process/status/{job_id} for
progress/result. This is what makes /process not block for however long
the LLM provider chain takes — previously a slow Gemini fallback could hold
an HTTP request open for a minute-plus.

Connects to the isolated caseweave-redis container (port 6381) — separate
from this machine's other Redis instances used by unrelated projects.
"""
from pathlib import Path

import redis
from rq import Queue
from rq.job import Job

from secrets_store import get_secret


def get_redis_connection():
    host = get_secret("REDIS_HOST") or "127.0.0.1"
    port = int(get_secret("REDIS_PORT") or 6381)
    return redis.Redis(host=host, port=port)


def get_queue() -> Queue:
    return Queue("caseweave-process", connection=get_redis_connection())


def get_job_status(job_id: str) -> dict:
    conn = get_redis_connection()
    try:
        job = Job.fetch(job_id, connection=conn)
    except Exception:
        return {"status": "not_found"}

    result = {"job_id": job_id, "status": job.get_status()}
    if job.is_finished:
        result["result"] = job.result
    elif job.is_failed:
        result["error"] = str(job.exc_info)[-2000:] if job.exc_info else "unknown error"
    return result


def run_process_job(case_id: str, legal_query: str | None):
    """
    The actual pipeline work, moved here from api.py so the RQ worker
    process can import and execute it by reference (RQ serializes jobs as
    a module path + args, not a closure — the function needs to live in an
    importable module, not be defined inline inside a FastAPI route).
    """
    from pathlib import Path as _Path

    from db import get_conn
    from storage import get_object_path
    from pipeline.observe import run_observation_engine
    from pipeline.timeline import build_timeline
    from pipeline.discrepancy import detect_discrepancies
    from pipeline.legal import search_legal_corpus
    from pipeline.scenarios import generate_scenarios
    from pipeline.report import generate_report
    from pipeline.report_pdf import generate_report_pdf
    from pipeline.timeline_html import render_timeline_html
    from pipeline.case_chat import index_case_evidence
    from pipeline.entities import resolve_entities
    from pipeline.incident_reconstruction import reconstruct_incident
    import backup as backup_module

    conn = get_conn()
    case = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    if not case:
        conn.close()
        raise ValueError(f"case not found: {case_id}")
    rows = conn.execute("SELECT * FROM evidence_items WHERE case_id=?", (case_id,)).fetchall()
    conn.close()

    # Stage 1: turn every evidence file (text, logs, PDFs, image OCR, audio,
    # video) into text for the observation engine. A file that fails to
    # extract is skipped and audited, not allowed to fail the whole run.
    import tempfile
    from db import append_audit_event
    from pipeline.extract import evidence_to_text

    evidence_items = []
    extraction_report = []
    work_root = _Path(tempfile.mkdtemp(prefix=f"cw_extract_{case_id}_"))
    for r in rows:
        path = get_object_path(case_id, r["evidence_id"], r["filename"])
        try:
            text, method = evidence_to_text(path, r["evidence_type"], work_root)
        except Exception as e:
            text, method = None, f"failed: {str(e)[:200]}"
        extraction_report.append({"evidence_id": r["evidence_id"], "filename": r["filename"], "method": method,
                                  "extracted": text is not None})
        if text is None:
            continue
        evidence_items.append({"evidence_id": r["evidence_id"], "path": path,
                               "evidence_type": r["evidence_type"], "content": text})

    import shutil
    shutil.rmtree(work_root, ignore_errors=True)  # extracted frames/audio are intermediates, not evidence

    log_conn = get_conn()
    for rep in extraction_report:
        action = f"extracted_{rep['method']}" if rep["extracted"] else f"extraction_skipped_{rep['method']}"
        append_audit_event(log_conn, case_id, "system", action[:128], rep["evidence_id"])
    log_conn.close()

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
    scenarios = generate_scenarios(conflicts)
    legal_results = search_legal_corpus(legal_query) if legal_query else []
    index_case_evidence(case_id)

    try:
        reconstruction = reconstruct_incident(
            case_id, timeline_events, entity_result["entities"], entity_result["relationships"],
            conflicts, evidence_links,
        )
    except Exception:
        reconstruction = None  # non-fatal: Stage 9a is additive, not required for a usable report

    backend_dir = _Path(__file__).parent
    report_path = backend_dir / f"output_report_{case_id}.md"
    generate_report(case_id, timeline_events, conflicts, scenarios, legal_results, report_path, reconstruction)

    pdf_path = backend_dir / f"output_report_{case_id}.pdf"
    generate_report_pdf(case_id, timeline_events, conflicts, scenarios, legal_results, pdf_path, reconstruction)

    html_path = backend_dir / f"timeline_{case_id}.html"
    render_timeline_html(case_id, case["title"], timeline_events, conflicts, html_path)

    try:
        backup_module.run_backup()
    except Exception:
        pass  # backup failure shouldn't fail the whole processing job

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
        "report_path": str(report_path),
        "pdf_report_path": str(pdf_path),
        "timeline_html_path": str(html_path),
    }
