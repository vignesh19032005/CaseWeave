"""
Stage 0 — FastAPI backend. Real HTTP API over the pipeline, CORS-enabled for
the Next.js frontend. Run: uvicorn api:app --reload --port 8010

Stage 12 — real auth/RBAC enforced on every mutating/sensitive endpoint.
Pilot-grade minimal: JWT login, per-endpoint role checks. No SSO, no
encrypted secrets vault — see PLAN.md's "pilot-grade minimal" line.
"""
import datetime
import json
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, FileResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from db import init_db, get_conn, file_hash, append_audit_event, verify_audit_chain
from storage import put_object, get_object_path
from pipeline.timeline import get_timeline as read_timeline
from pipeline.discrepancy import update_review_status, get_conflict_reviews
from pipeline.scene import generate_scene_jsx
from pipeline.entities import resolve_entities
from pipeline.case_chat import ask_case
from pipeline.incident_reconstruction import reconstruct_incident
import auth
import upload_validation
from logging_config import get_logger, log_event

_log = get_logger("api")

init_db()


def _bootstrap_admin():
    """First-run only: creates a default admin account if none exists, so
    there's a way to log in at all. Printed once, change immediately."""
    conn = get_conn()
    existing = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
    conn.close()
    if not existing:
        auth.create_user("admin", "changeme123", "admin")
        print("[BOOTSTRAP] Created default admin account: admin / changeme123 — change this immediately.")


_bootstrap_admin()

app = FastAPI(title="CaseWeave API", version="0.3.0")

# Stage 16: rate limiting on the LLM-budget-burning endpoints — stops one
# compromised account or runaway client from draining the Meta/Groq/Gemini
# quota or DoS-ing the service. Keyed by remote IP (good enough for a
# single-deployment pilot; per-user keying would need Stage 20's real
# infra to track fairly across multiple server instances).
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

import os
from secrets_store import get_secret

# Configurable CORS origins for station/local network access (e.g. ALLOWED_ORIGINS="http://192.168.1.50:3000,http://localhost:3000")
raw_origins = get_secret("ALLOWED_ORIGINS") or os.environ.get("ALLOWED_ORIGINS", "")
allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
if not allowed_origins:
    allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Evidence originals are served only through the authenticated
# /cases/{id}/evidence/{eid}/file endpoint below — no public static mount.


# ---------------------------------------------------------------- Auth ----

class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/register")
def register(body: RegisterRequest, user: dict = Depends(auth.get_current_user)):
    auth.enforce_permission(user, "manage_users")
    try:
        user_id = auth.create_user(body.username, body.password, body.role)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"user_id": user_id, "username": body.username, "role": body.role}


@app.post("/auth/login")
def login(body: LoginRequest):
    try:
        user = auth.authenticate(body.username, body.password)
    except ValueError as e:
        raise HTTPException(401, str(e))
    token = auth.create_token(user)
    return {"access_token": token, "token_type": "bearer", "role": user["role"], "username": user["username"]}


@app.get("/auth/me")
def me(user: dict = Depends(auth.get_current_user)):
    return user


# ---------------------------------------------------------------- Cases ----

class CaseCreate(BaseModel):
    title: str


class CaseOut(BaseModel):
    case_id: str
    title: str
    created_at: str


def _classify_evidence_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".json":
        return "structured_log"
    if suffix in (".txt", ".md"):
        return "text_document"
    if suffix == ".pdf":
        return "pdf"
    if suffix in (".jpg", ".jpeg", ".png"):
        return "image"
    if suffix in (".mp4", ".mov", ".avi"):
        return "video"
    if suffix in (".wav", ".mp3", ".m4a"):
        return "audio"
    return "unknown"


@app.post("/cases", response_model=CaseOut)
def create_case(body: CaseCreate, user: dict = Depends(auth.get_current_user)):
    case_id = f"CW-{uuid.uuid4().hex[:6].upper()}"
    created_at = datetime.datetime.utcnow().isoformat()

    conn = get_conn()
    conn.execute("INSERT INTO cases VALUES (?,?,?)", (case_id, body.title, created_at))
    conn.commit()
    append_audit_event(conn, case_id, user["role"], "case_created", case_id)
    conn.close()
    return CaseOut(case_id=case_id, title=body.title, created_at=created_at)


@app.get("/cases")
def list_cases(user: dict = Depends(auth.get_current_user)):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/cases/{case_id}")
def get_case(case_id: str, user: dict = Depends(auth.get_current_user)):
    conn = get_conn()
    case = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    if not case:
        conn.close()
        raise HTTPException(404, "case not found")
    evidence = conn.execute("SELECT * FROM evidence_items WHERE case_id=?", (case_id,)).fetchall()
    conn.close()
    return {"case": dict(case), "evidence": [dict(e) for e in evidence]}


@app.delete("/cases/{case_id}")
def delete_case(case_id: str, user: dict = Depends(auth.get_current_user)):
    """Permanently removes a case: all DB rows, stored evidence files, and
    the case-evidence chat index. No undo — the UI confirms before calling
    this. Audit events for the case are deleted too (there's no case left
    for them to attest to); this is a real destructive admin action, not
    something Stage 18's future retention policy replaces."""
    auth.enforce_permission(user, "delete_case")
    conn = get_conn()
    case = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    if not case:
        conn.close()
        raise HTTPException(404, "case not found")
    conn.execute("SET FOREIGN_KEY_CHECKS=0")
    for table in [
        "evidence_items", "observations", "entities", "entity_mentions", "relationships",
        "timeline_events", "conflicts", "evidence_links", "conflict_reviews", "audit_events", "cases",
    ]:
        conn.execute(f"DELETE FROM {table} WHERE case_id=?", (case_id,))
    conn.execute("SET FOREIGN_KEY_CHECKS=1")
    conn.commit()
    conn.close()

    shutil.rmtree(Path(__file__).parent / "object_store" / case_id, ignore_errors=True)
    for report_file in [f"output_report_{case_id}.md", f"output_report_{case_id}.pdf", f"timeline_{case_id}.html"]:
        (Path(__file__).parent / report_file).unlink(missing_ok=True)
    try:
        import chromadb
        from pipeline.legal import CHROMA_DIR
        chromadb.PersistentClient(path=str(CHROMA_DIR)).delete_collection(f"case_evidence_{case_id}")
    except Exception:
        pass  # chat was never indexed for this case, or already gone

    log_event(_log, "info", "case deleted", case_id=case_id, by_user=user["username"])
    return {"case_id": case_id, "deleted": True}


@app.post("/cases/{case_id}/evidence")
@limiter.limit("20/minute")
async def upload_evidence(request: Request, case_id: str, file: UploadFile = File(...), user: dict = Depends(auth.get_current_user)):
    auth.enforce_permission(user, "upload_evidence")

    conn = get_conn()
    case = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    if not case:
        conn.close()
        raise HTTPException(404, "case not found")

    # Strip any client-supplied directory components ("../../x.txt") so the
    # temp write and stored name can't escape their directories.
    safe_name = Path(file.filename or "").name
    if not safe_name or safe_name in (".", ".."):
        conn.close()
        raise HTTPException(400, "invalid filename")

    evidence_type = _classify_evidence_type(safe_name)
    evidence_id = f"EV-{case_id}-{uuid.uuid4().hex[:8]}"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / safe_name
        size = 0
        header = b""
        with open(tmp_path, "wb") as f:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > upload_validation.MAX_UPLOAD_SIZE_BYTES:
                    conn.close()
                    raise HTTPException(413, f"file exceeds {upload_validation.MAX_UPLOAD_SIZE_BYTES} byte limit")
                if len(header) < 32:
                    header += chunk[: 32 - len(header)]
                f.write(chunk)

        try:
            upload_validation.validate_size(size, safe_name)
            upload_validation.validate_magic_bytes(header, evidence_type, safe_name)
        except upload_validation.UploadValidationError as e:
            conn.close()
            log_event(_log, "warning", "upload rejected by validation", filename=safe_name, reason=str(e))
            raise HTTPException(400, str(e))

        storage_meta = put_object(case_id, evidence_id, tmp_path)

    conn.execute(
        "INSERT INTO evidence_items VALUES (?,?,?,?,?,?)",
        (evidence_id, case_id, safe_name, storage_meta["sha256"], evidence_type, "uploaded"),
    )
    conn.commit()
    append_audit_event(conn, case_id, user["role"], "evidence_uploaded", evidence_id)
    conn.close()

    return {
        "evidence_id": evidence_id,
        "filename": safe_name,
        "evidence_type": evidence_type,
        "sha256": storage_meta["sha256"],
        "size_bytes": storage_meta["size_bytes"],
    }


@app.get("/cases/{case_id}/evidence")
def list_evidence(case_id: str, user: dict = Depends(auth.get_current_user)):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM evidence_items WHERE case_id=?", (case_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_evidence_row(case_id: str, evidence_id: str) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM evidence_items WHERE case_id=? AND evidence_id=?", (case_id, evidence_id)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "evidence item not found")
    return row


@app.get("/cases/{case_id}/evidence/{evidence_id}/file")
def get_evidence_file(case_id: str, evidence_id: str, user: dict = Depends(auth.get_current_user)):
    auth.enforce_permission(user, "view_case")
    row = _get_evidence_row(case_id, evidence_id)
    try:
        path = get_object_path(case_id, evidence_id, row["filename"])
    except FileNotFoundError:
        raise HTTPException(404, "stored evidence file missing")
    return FileResponse(path, filename=row["filename"])


# --------------------------------------------------------- Main pipeline ----

class ProcessRequest(BaseModel):
    legal_query: Optional[str] = None


@app.post("/cases/{case_id}/process")
@limiter.limit("5/minute")
def process_case(request: Request, case_id: str, body: ProcessRequest = ProcessRequest(), user: dict = Depends(auth.get_current_user)):
    """Enqueues Stages 2-10 as a background job instead of running them on
    the request thread — a slow LLM provider fallback used to hold this
    request open for a minute-plus; now it returns a job_id immediately and
    the client polls /process/status/{job_id}. Requires a worker process
    running: `python worker.py` (see worker.py / job_queue.py).

    JSON body, not multipart form: python-multipart raises "There was an
    error parsing the body" on a genuinely empty multipart body (zero
    parts) — exactly what a browser sends when there's no legal query —
    so this used to 400 on every no-query run. JSON has no such edge case
    and matches every other endpoint in this file."""
    legal_query = body.legal_query
    auth.enforce_permission(user, "upload_evidence")
    conn = get_conn()
    case = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    if not case:
        conn.close()
        raise HTTPException(404, "case not found")
    conn.close()

    from job_queue import get_queue, run_process_job

    queue = get_queue()
    # A real case makes ~40 sequential LLM calls (observations per document,
    # entity resolution, 3 debate calls per candidate pair, scenarios,
    # reconstruction) — measured ~11 min for the 5-document demo case, so
    # 600s was too tight.
    job = queue.enqueue(run_process_job, case_id, legal_query, job_timeout=1800)

    log_event(_log, "info", "process job enqueued", case_id=case_id, job_id=job.id)
    return {"job_id": job.id, "status": "queued"}


@app.get("/cases/{case_id}/process/status/{job_id}")
def process_status(case_id: str, job_id: str, user: dict = Depends(auth.get_current_user)):
    from job_queue import get_job_status

    return get_job_status(job_id)


@app.get("/cases/{case_id}/timeline")
def get_timeline(case_id: str, user: dict = Depends(auth.get_current_user)):
    return read_timeline(case_id)


@app.get("/cases/{case_id}/audit")
def get_audit(case_id: str, user: dict = Depends(auth.get_current_user)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM audit_events WHERE case_id=? ORDER BY timestamp ASC", (case_id,)
    ).fetchall()
    chain_ok = verify_audit_chain(conn, case_id)
    conn.close()
    return {"events": [dict(r) for r in rows], "chain_integrity": "PASSED" if chain_ok else "FAILED"}


# -------------------------------------------------------- Stage 4a / 4b ----

class ReviewStatusUpdate(BaseModel):
    status: str
    reason: str


@app.patch("/cases/{case_id}/conflicts/{conflict_id}/review")
def patch_review_status(case_id: str, conflict_id: str, body: ReviewStatusUpdate, user: dict = Depends(auth.get_current_user)):
    auth.enforce_permission(user, "confirm_conflict")
    try:
        update_review_status(case_id, conflict_id, body.status, body.reason, user["username"], user["role"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"conflict_id": conflict_id, "review_status": body.status}


@app.get("/cases/{case_id}/conflicts/{conflict_id}/reviews")
def get_conflict_review_history(case_id: str, conflict_id: str, user: dict = Depends(auth.get_current_user)):
    return get_conflict_reviews(case_id, conflict_id)


@app.get("/cases/{case_id}/evidence-links")
def get_evidence_links(case_id: str, user: dict = Depends(auth.get_current_user)):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM evidence_links WHERE case_id=?", (case_id,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("transcript"):
            try:
                d["transcript"] = json.loads(d["transcript"])
            except (TypeError, ValueError):
                pass
        out.append(d)
    return out


@app.get("/cases/{case_id}/conflicts")
def get_conflicts(case_id: str, user: dict = Depends(auth.get_current_user)):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM conflicts WHERE case_id=?", (case_id,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("transcript"):
            try:
                d["transcript"] = json.loads(d["transcript"])
            except (TypeError, ValueError):
                pass
        out.append(d)
    return out


# --------------------------------------------------------------- Stage 2.5 ----

class ChatTurn(BaseModel):
    question: str
    answer: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatTurn] = []


@app.post("/cases/{case_id}/chat")
@limiter.limit("15/minute")
def chat_with_case(request: Request, case_id: str, body: ChatRequest, user: dict = Depends(auth.get_current_user)):
    try:
        return ask_case(case_id, body.question, [h.model_dump() for h in body.history])
    except Exception as e:
        raise HTTPException(500, str(e))


# ----------------------------------------------------------------- Stage 11 ----

@app.post("/cases/{case_id}/entities/resolve")
def resolve_case_entities(case_id: str, user: dict = Depends(auth.get_current_user)):
    auth.enforce_permission(user, "upload_evidence")
    try:
        return resolve_entities(case_id)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/cases/{case_id}/entities")
def get_entities(case_id: str, user: dict = Depends(auth.get_current_user)):
    conn = get_conn()
    entities = conn.execute("SELECT * FROM entities WHERE case_id=?", (case_id,)).fetchall()
    relationships = conn.execute("SELECT * FROM relationships WHERE case_id=?", (case_id,)).fetchall()
    mentions = conn.execute(
        "SELECT entity_id, observation_id FROM entity_mentions WHERE case_id=?", (case_id,)
    ).fetchall()
    conn.close()
    return {
        "entities": [dict(e) for e in entities],
        "relationships": [dict(r) for r in relationships],
        "mentions": [dict(m) for m in mentions],
    }


# ----------------------------------------------------------------- Stage 9a ----

@app.post("/cases/{case_id}/reconstruct")
def reconstruct_case(case_id: str, user: dict = Depends(auth.get_current_user)):
    conn = get_conn()
    entities = [dict(r) for r in conn.execute("SELECT * FROM entities WHERE case_id=?", (case_id,)).fetchall()]
    relationships_raw = conn.execute("SELECT * FROM relationships WHERE case_id=?", (case_id,)).fetchall()
    conflicts_raw = conn.execute("SELECT * FROM conflicts WHERE case_id=?", (case_id,)).fetchall()
    links_raw = conn.execute("SELECT * FROM evidence_links WHERE case_id=?", (case_id,)).fetchall()
    conn.close()

    if not entities:
        raise HTTPException(400, "no entities resolved yet — call /entities/resolve first")

    timeline_events = read_timeline(case_id)
    relationships = [{"from": r["from_entity_id"], "to": r["to_entity_id"], "type": r["relationship_type"]} for r in relationships_raw]
    conflicts = [{"claim_a": c["claim_a"], "claim_b": c["claim_b"], "nature_of_conflict": c["nature_of_conflict"] or c["question"]} for c in conflicts_raw]
    evidence_links = [{"claim_a": l["claim_a"], "claim_b": l["claim_b"], "link_type": l["link_type"]} for l in links_raw]

    try:
        result = reconstruct_incident(case_id, timeline_events, entities, relationships, conflicts, evidence_links)
    except Exception as e:
        raise HTTPException(500, str(e))

    conn = get_conn()
    append_audit_event(conn, case_id, user["role"], "incident_reconstruction_run", case_id)
    conn.close()
    return result


# ------------------------------------------------------------------ Scene ----

class SceneRequest(BaseModel):
    description: str
    width_m: float
    length_m: float
    height_m: float


@app.post("/cases/{case_id}/scene")
def create_scene(case_id: str, body: SceneRequest, user: dict = Depends(auth.get_current_user)):
    result = generate_scene_jsx(
        body.description,
        {"width_m": body.width_m, "length_m": body.length_m, "height_m": body.height_m},
    )
    return result


# ----------------------------------------------------------- Segmentation (Stage 8) ----

class SegmentRequest(BaseModel):
    prompt: str


@app.post("/cases/{case_id}/evidence/{evidence_id}/segment")
def segment_evidence(case_id: str, evidence_id: str, body: SegmentRequest, user: dict = Depends(auth.get_current_user)):
    """Stage 8: SAM 3.1 object segmentation on an image evidence item."""
    row = _get_evidence_row(case_id, evidence_id)
    if row.get("evidence_type") != "image":
        raise HTTPException(400, "Segmentation is only supported on image evidence")

    from storage import get_object_path
    from pipeline.segment import segment_image

    img_path = get_object_path(case_id, evidence_id, row["filename"])
    try:
        res = segment_image(img_path, body.prompt)
    except Exception as e:
        raise HTTPException(502, f"Segmentation inference failed: {e}")

    conn = get_conn()
    append_audit_event(conn, case_id, user["role"], "image_segmented", f"{evidence_id}:{body.prompt}")
    conn.close()
    return res


@app.get("/cases/{case_id}/evidence/{evidence_id}/certificate")
def download_evidence_certificate(case_id: str, evidence_id: str, user: dict = Depends(auth.get_current_user)):
    auth.enforce_permission(user, "export_report")
    _get_evidence_row(case_id, evidence_id)  # 404s if not found
    from pipeline.certificate_pdf import generate_evidence_certificate

    tmp_path = Path(__file__).parent / f"_tmp_cert_{case_id}_{evidence_id}.pdf"
    try:
        generate_evidence_certificate(case_id, evidence_id, tmp_path)
        pdf_bytes = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)

    conn = get_conn()
    append_audit_event(conn, case_id, user["role"], "evidence_certificate_generated", evidence_id)
    conn.close()

    from fastapi.responses import Response
    return Response(
        pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Draft_Certificate_{evidence_id}.pdf"'},
    )


# --------------------------------------------------------------- Reports ----

@app.get("/cases/{case_id}/report")
def download_report(case_id: str, user: dict = Depends(auth.get_current_user)):
    auth.enforce_permission(user, "export_report")
    report_path = Path(__file__).parent / f"output_report_{case_id}.md"
    if not report_path.exists():
        raise HTTPException(404, "no report generated yet — call /process first")
    conn = get_conn()
    append_audit_event(conn, case_id, user["role"], "report_exported", case_id)
    conn.close()
    return PlainTextResponse(report_path.read_text(encoding="utf-8"), media_type="text/markdown")


@app.get("/cases/{case_id}/report/pdf")
def download_report_pdf(case_id: str, user: dict = Depends(auth.get_current_user)):
    auth.enforce_permission(user, "export_report")
    pdf_path = Path(__file__).parent / f"output_report_{case_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "no PDF report generated yet — call /process first")
    conn = get_conn()
    append_audit_event(conn, case_id, user["role"], "pdf_report_exported", case_id)
    conn.close()
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"CaseWeave_Report_{case_id}.pdf")


@app.get("/health")
def health():
    return {"status": "ok"}
