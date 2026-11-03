"""
Stage 0 — FastAPI backend. Real HTTP API over the pipeline, CORS-enabled for
the Next.js frontend. Run: uvicorn api:app --port 8010

Stage 12 — real auth/RBAC enforced on EVERY endpoint that reads or changes a case.
Pilot-grade: JWT login, role looked up in the database on each request, per-endpoint permission checks, no SSO.
The model is single-department: any signed-in user with the right role can see every case (there is no
per-case ownership), and the audit trail records who did what.
"""
import datetime
import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, FileResponse, Response
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from db import init_db, get_conn, append_audit_event, append_audit_event_txn, verify_audit_chain_detail, utcnow
from storage import put_object, require_intact, delete_case_objects, IntegrityError
from pipeline.timeline import get_timeline as read_timeline
from pipeline.discrepancy import update_review_status, get_conflict_reviews
from pipeline.entities import resolve_entities
from pipeline.case_chat import ask_case, drop_case_index
from pipeline.incident_reconstruction import reconstruct_incident
import auth
import upload_validation
from llm_client import LLMUnavailableError
from logging_config import get_logger, log_event
from secrets_store import get_secret

_log = get_logger("api")

init_db()
_note = auth.bootstrap_admin()
if _note:
    _log.warning(_note)
_flagged = auth.flag_default_passwords()
if _flagged:
    _log.warning("%d account(s) still use the shipped default password and must change it at next sign-in.", _flagged)

app = FastAPI(title="CaseWeave API", version="0.4.0")


def _rate_key(request: Request) -> str:
    """Rate limits are per signed-in user when there is a valid token, otherwise per client address."""
    header = request.headers.get("authorization", "")
    if header.startswith("Bearer "):
        try:
            return "user:" + str(auth.decode_token(header[7:].strip()).get("user_id"))
        except HTTPException:
            pass
    return get_remote_address(request)


# Stage 16: rate limiting on the LLM-budget-burning endpoints — stops one compromised account or runaway
# client from draining the provider quota or DoS-ing the service.
limiter = Limiter(key_func=_rate_key)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


# Evidence originals are served only through the authenticated
# /cases/{id}/evidence/{eid}/file endpoint below — no public static mount.


# ----------------------------------------------------------------- helpers ----

def _audit(case_id: str, user: dict, action: str, target: str) -> None:
    """Records who did what, with their username (not only their role)."""
    with get_conn() as conn:
        append_audit_event(conn, case_id, user["role"], action, target[:128], actor_user=user["username"])


def _require_case(case_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    if not row:
        raise HTTPException(404, "case not found")
    return dict(row)


def _server_error(what: str, exc: Exception) -> HTTPException:
    """Logs the real error on the server and gives the client a message that reveals nothing internal."""
    _log.exception("%s failed", what)
    if isinstance(exc, LLMUnavailableError):
        return HTTPException(503, "The language model could not be reached. Try again shortly.")
    return HTTPException(500, f"{what} failed. The error was logged on the server.")


# ---------------------------------------------------------------- Auth ----

class RegisterRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=200)
    role: str = Field(max_length=32)


class LoginRequest(BaseModel):
    username: str = Field(max_length=128)
    password: str = Field(max_length=200)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(max_length=200)


# Repeated wrong passwords for one username lock that username for a few minutes (in this process).
_FAILED: dict = {}
_failed_lock = threading.Lock()
LOCK_AFTER, LOCK_WINDOW_S = 5, 300


def _locked(username: str) -> bool:
    with _failed_lock:
        hits = [t for t in _FAILED.get(username.lower(), []) if time.time() - t < LOCK_WINDOW_S]
        _FAILED[username.lower()] = hits
        return len(hits) >= LOCK_AFTER


def _record_failure(username: str) -> None:
    with _failed_lock:
        _FAILED.setdefault(username.lower(), []).append(time.time())


@app.post("/auth/register")
def register(body: RegisterRequest, user: dict = Depends(auth.require("manage_users"))):
    try:
        user_id = auth.create_user(body.username, body.password, body.role)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"user_id": user_id, "username": body.username, "role": body.role}


@app.post("/auth/login")
@limiter.limit("10/minute", key_func=get_remote_address)
def login(request: Request, body: LoginRequest):
    if _locked(body.username):
        raise HTTPException(429, "Too many failed sign-ins for this account. Try again in a few minutes.")
    try:
        user = auth.authenticate(body.username, body.password)
    except ValueError as e:
        _record_failure(body.username)
        raise HTTPException(401, str(e))
    with _failed_lock:
        _FAILED.pop(body.username.lower(), None)
    token = auth.create_token(user)
    return {"access_token": token, "token_type": "bearer", "role": user["role"], "username": user["username"],
            "must_change_password": user["must_change_password"]}


@app.get("/auth/me")
def me(user: dict = Depends(auth.get_user_even_if_password_change_pending)):
    return user


@app.post("/auth/change-password")
@limiter.limit("10/minute")
def change_password(request: Request, body: ChangePasswordRequest, user: dict = Depends(auth.get_user_even_if_password_change_pending)):
    try:
        auth.change_password(user["user_id"], body.old_password, body.new_password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    fresh = auth.authenticate(user["username"], body.new_password)
    return {"access_token": auth.create_token(fresh), "token_type": "bearer", "role": fresh["role"], "username": fresh["username"],
            "must_change_password": False}


@app.get("/auth/users")
def list_users(user: dict = Depends(auth.require("manage_users"))):
    return auth.list_users()


@app.post("/auth/users/{user_id}/reset-password")
def reset_user_password(user_id: str, body: ResetPasswordRequest, user: dict = Depends(auth.require("manage_users"))):
    try:
        auth.admin_reset_password(user_id, body.new_password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"user_id": user_id, "must_change_password": True}


@app.delete("/auth/users/{user_id}")
def delete_user(user_id: str, user: dict = Depends(auth.require("manage_users"))):
    try:
        auth.delete_user(user_id, user["user_id"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"user_id": user_id, "deleted": True}


# ---------------------------------------------------------------- Cases ----

class CaseCreate(BaseModel):
    title: str = Field(max_length=200)


class CaseOut(BaseModel):
    case_id: str
    title: str
    created_at: str


@app.post("/cases", response_model=CaseOut)
def create_case(body: CaseCreate, user: dict = Depends(auth.require("create_case"))):
    title = " ".join((body.title or "").split()) or "Untitled Case"
    case_id = f"CW-{uuid.uuid4().hex[:6].upper()}"
    created_at = utcnow().isoformat()
    with get_conn() as conn:
        conn.execute("INSERT INTO cases (case_id, title, created_at) VALUES (?,?,?)", (case_id, title, created_at))
        conn.commit()
    _audit(case_id, user, "case_created", case_id)
    return CaseOut(case_id=case_id, title=title, created_at=created_at)


@app.get("/cases")
def list_cases(user: dict = Depends(auth.require("view_case"))):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


@app.get("/cases/{case_id}")
def get_case(case_id: str, user: dict = Depends(auth.require("view_case"))):
    case = _require_case(case_id)
    with get_conn() as conn:
        evidence = conn.execute("SELECT * FROM evidence_items WHERE case_id=?", (case_id,)).fetchall()
    return {"case": case, "evidence": [dict(e) for e in evidence]}


_CASE_TABLES = [
    "evidence_items", "observations", "entities", "entity_mentions", "relationships",
    "timeline_events", "conflicts", "evidence_links", "conflict_reviews",
    "sandbox_scenarios", "sandbox_runs", "sandbox_photo_links", "sandbox_reviews", "case_narratives", "case_signatures", "cases",
]


@app.delete("/cases/{case_id}")
def delete_case(case_id: str, user: dict = Depends(auth.require("delete_case"))):
    """Permanently removes a case: all DB rows, stored evidence files, the case-evidence chat index and the
    reports. No undo — the UI confirms before calling this. The case's audit trail is KEPT, and a final
    "case_deleted" event is written in the same transaction as the deletion, so who deleted what and when stays
    on record and the record cannot exist without the deletion or the reverse."""
    _require_case(case_id)
    from job_queue import active_job_for_case
    try:
        if active_job_for_case(case_id):
            raise HTTPException(409, "This case is being processed. Wait for it to finish before deleting it.")
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - Redis down: nothing can be running through the queue
        pass
    release = None
    with get_conn() as conn:
        try:
            for table in _CASE_TABLES:
                conn.execute(f"DELETE FROM {table} WHERE case_id=?", (case_id,))
            # audit_events are deliberately NOT deleted: the chain of custody outlives the case.
            _, release = append_audit_event_txn(conn, case_id, user["role"], "case_deleted", f"{case_id}|by:{user['username']}"[:128], actor_user=user["username"])
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if release:
                release()

    try:
        delete_case_objects(case_id)
    except FileNotFoundError:
        pass
    from pipeline.report_refresh import delete_report_files
    delete_report_files(case_id)
    drop_case_index(case_id)
    try:
        import chromadb
        from pipeline.legal import CHROMA_DIR
        chromadb.PersistentClient(path=str(CHROMA_DIR)).get_or_create_collection("case_patterns").delete(ids=[case_id])
    except Exception:  # noqa: BLE001 - never indexed for patterns
        pass

    log_event(_log, "info", "case deleted", case_id=case_id, by_user=user["username"])
    return {"case_id": case_id, "deleted": True}


_WINDOWS_BAD = re.compile(r'[<>:"|?*\x00-\x1f]')


def _clean_filename(raw: Optional[str]) -> str:
    """A bare, filesystem-safe file name: no directories (either slash style), no characters Windows rejects."""
    name = re.split(r"[\\/]", raw or "")[-1].strip().strip(".")
    name = _WINDOWS_BAD.sub("_", name)
    stem, dot, ext = name.rpartition(".")
    if dot and len(name) > 150:
        name = stem[: 150 - len(ext) - 1] + "." + ext
    return name[:150]


@app.post("/cases/{case_id}/evidence")
@limiter.limit("60/minute")
async def upload_evidence(request: Request, case_id: str, file: UploadFile = File(...), user: dict = Depends(auth.require("upload_evidence"))):
    _require_case(case_id)
    safe_name = _clean_filename(file.filename)
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(400, "invalid filename")
    try:
        evidence_type = upload_validation.classify_evidence_type(safe_name)
    except upload_validation.UploadValidationError as e:
        raise HTTPException(400, str(e))
    evidence_id = f"EV-{case_id}-{uuid.uuid4().hex[:8]}"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / safe_name
        size = 0
        header = b""
        with open(tmp_path, "wb") as f:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > upload_validation.MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(413, f"file exceeds {upload_validation.MAX_UPLOAD_SIZE_BYTES} byte limit")
                if len(header) < 32:
                    header += chunk[: 32 - len(header)]
                f.write(chunk)

        try:
            upload_validation.validate_size(size, safe_name)
            upload_validation.validate_magic_bytes(header, evidence_type, safe_name)
            upload_validation.validate_text_content(tmp_path, evidence_type, safe_name)
        except upload_validation.UploadValidationError as e:
            log_event(_log, "warning", "upload rejected by validation", filename=safe_name, reason=str(e))
            raise HTTPException(400, str(e))

        from db import file_hash
        sha = file_hash(tmp_path)
        with get_conn() as conn:
            dup = conn.execute("SELECT evidence_id, filename FROM evidence_items WHERE case_id=? AND file_hash=?", (case_id, sha)).fetchone()
        if dup:
            raise HTTPException(409, f"This exact file is already in the case as {dup['evidence_id']} ({dup['filename']}).")

        storage_meta = put_object(case_id, evidence_id, tmp_path)

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO evidence_items (evidence_id, case_id, filename, file_hash, evidence_type, status) VALUES (?,?,?,?,?,?)",
            (evidence_id, case_id, safe_name, storage_meta["sha256"], evidence_type, "uploaded"),
        )
        conn.commit()
    _audit(case_id, user, "evidence_uploaded", evidence_id)

    return {
        "evidence_id": evidence_id,
        "filename": safe_name,
        "evidence_type": evidence_type,
        "sha256": storage_meta["sha256"],
        "size_bytes": storage_meta["size_bytes"],
    }


@app.get("/cases/{case_id}/evidence")
def list_evidence(case_id: str, user: dict = Depends(auth.require("view_case"))):
    _require_case(case_id)
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM evidence_items WHERE case_id=?", (case_id,)).fetchall()
    return [dict(r) for r in rows]


def _get_evidence_row(case_id: str, evidence_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM evidence_items WHERE case_id=? AND evidence_id=?", (case_id, evidence_id)
        ).fetchone()
    if not row:
        raise HTTPException(404, "evidence item not found")
    return dict(row)


def _intact_path(case_id: str, row: dict, user: dict) -> Path:
    """The stored original, only if it still matches the hash recorded at upload. A mismatch is audited and refused."""
    try:
        return require_intact(case_id, row["evidence_id"], row["filename"], row["file_hash"])
    except FileNotFoundError:
        raise HTTPException(404, "stored evidence file missing")
    except IntegrityError:
        _audit(case_id, user, "evidence_integrity_failure", row["evidence_id"])
        raise HTTPException(409, "This file no longer matches the SHA-256 hash recorded when it was uploaded, so it is not served or analysed. Report this to the case administrator.")


@app.get("/cases/{case_id}/evidence/{evidence_id}/file")
def get_evidence_file(case_id: str, evidence_id: str, user: dict = Depends(auth.require("view_case"))):
    row = _get_evidence_row(case_id, evidence_id)
    path = _intact_path(case_id, row, user)
    _audit(case_id, user, "evidence_file_accessed", evidence_id)
    return FileResponse(path, filename=row["filename"])


# --------------------------------------------------------- Main pipeline ----

class ProcessRequest(BaseModel):
    legal_query: Optional[str] = Field(default=None, max_length=1000)


@app.post("/cases/{case_id}/process")
@limiter.limit("5/minute")
def process_case(request: Request, case_id: str, body: ProcessRequest = ProcessRequest(), user: dict = Depends(auth.require("upload_evidence"))):
    """Enqueues Stages 2-10 as a background job instead of running them on the request thread; returns a job_id
    immediately and the client polls /process/status/{job_id}. Requires a worker process: `python worker.py`.
    Only one job per case may be queued or running; a second request gets 409.

    JSON body, not multipart form: python-multipart raises "There was an error parsing the body" on a genuinely
    empty multipart body, which is exactly what a browser sends when there's no legal query."""
    _require_case(case_id)
    from job_queue import enqueue_process, CaseBusy
    try:
        job_id = enqueue_process(case_id, (body.legal_query or "").strip() or None)
    except CaseBusy as e:
        raise HTTPException(409, str(e))
    except Exception as e:  # noqa: BLE001 - Redis unreachable etc.
        raise _server_error("Starting the analysis", e)
    _audit(case_id, user, "analysis_started", job_id)
    log_event(_log, "info", "process job enqueued", case_id=case_id, job_id=job_id)
    return {"job_id": job_id, "status": "queued"}


@app.get("/cases/{case_id}/process/status/{job_id}")
def process_status(case_id: str, job_id: str, user: dict = Depends(auth.require("view_case"))):
    _require_case(case_id)
    from job_queue import get_job_status
    return get_job_status(job_id, case_id)


@app.get("/cases/{case_id}/timeline")
def get_timeline(case_id: str, user: dict = Depends(auth.require("view_case"))):
    _require_case(case_id)
    return read_timeline(case_id)


@app.get("/cases/{case_id}/audit")
def get_audit(case_id: str, user: dict = Depends(auth.require("view_case"))):
    _require_case(case_id)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_events WHERE case_id=? ORDER BY timestamp ASC", (case_id,)
        ).fetchall()
        detail = verify_audit_chain_detail(conn, case_id)
    return {"events": [dict(r) for r in rows], "chain_integrity": "PASSED" if detail["ok"] else "FAILED", "chain_detail": detail["reason"]}


# -------------------------------------------------------- Stage 4a / 4b ----

class ReviewStatusUpdate(BaseModel):
    status: str = Field(max_length=32)
    reason: str = Field(max_length=1000)


@app.patch("/cases/{case_id}/conflicts/{conflict_id}/review")
def patch_review_status(case_id: str, conflict_id: str, body: ReviewStatusUpdate, user: dict = Depends(auth.require("confirm_conflict"))):
    _require_case(case_id)
    try:
        update_review_status(case_id, conflict_id, body.status, body.reason, user["username"], user["role"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:  # the exported report carries the reviewer's decision
        from pipeline.report_refresh import refresh_reports
        refresh_reports(case_id)
    except Exception:  # noqa: BLE001 - the decision is saved either way
        _log.exception("could not refresh the report after a review")
    return {"conflict_id": conflict_id, "review_status": body.status}


@app.get("/cases/{case_id}/conflicts/{conflict_id}/reviews")
def get_conflict_review_history(case_id: str, conflict_id: str, user: dict = Depends(auth.require("view_case"))):
    _require_case(case_id)
    return get_conflict_reviews(case_id, conflict_id)


def _with_transcript(rows) -> list:
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


@app.get("/cases/{case_id}/evidence-links")
def get_evidence_links(case_id: str, user: dict = Depends(auth.require("view_case"))):
    _require_case(case_id)
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM evidence_links WHERE case_id=?", (case_id,)).fetchall()
    return _with_transcript(rows)


@app.get("/cases/{case_id}/conflicts")
def get_conflicts(case_id: str, user: dict = Depends(auth.require("view_case"))):
    _require_case(case_id)
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM conflicts WHERE case_id=?", (case_id,)).fetchall()
    return _with_transcript(rows)


# --------------------------------------------------------------- Stage 2.5 ----

class ChatTurn(BaseModel):
    question: str = Field(max_length=2000)
    answer: str = Field(max_length=6000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default=[], max_length=12)


@app.post("/cases/{case_id}/chat")
@limiter.limit("15/minute")
def chat_with_case(request: Request, case_id: str, body: ChatRequest, user: dict = Depends(auth.require("view_case"))):
    _require_case(case_id)
    try:
        return ask_case(case_id, body.question, [h.model_dump() for h in body.history])
    except Exception as e:  # noqa: BLE001
        raise _server_error("The answer", e)


# ----------------------------------------------------------------- Stage 11 ----

@app.post("/cases/{case_id}/entities/resolve")
@limiter.limit("5/minute")
def resolve_case_entities(request: Request, case_id: str, user: dict = Depends(auth.require("upload_evidence"))):
    _require_case(case_id)
    try:
        return resolve_entities(case_id)
    except Exception as e:  # noqa: BLE001
        raise _server_error("Entity resolution", e)


@app.get("/cases/{case_id}/entities")
def get_entities(case_id: str, user: dict = Depends(auth.require("view_case"))):
    _require_case(case_id)
    with get_conn() as conn:
        entities = conn.execute("SELECT * FROM entities WHERE case_id=?", (case_id,)).fetchall()
        relationships = conn.execute("SELECT * FROM relationships WHERE case_id=?", (case_id,)).fetchall()
        mentions = conn.execute("SELECT entity_id, observation_id FROM entity_mentions WHERE case_id=?", (case_id,)).fetchall()
    return {
        "entities": [dict(e) for e in entities],
        "relationships": [dict(r) for r in relationships],
        "mentions": [dict(m) for m in mentions],
    }


# ----------------------------------------------------------------- Stage 9a ----

@app.post("/cases/{case_id}/reconstruct")
@limiter.limit("5/minute")
def reconstruct_case(request: Request, case_id: str, user: dict = Depends(auth.require("generate_scenario"))):
    _require_case(case_id)
    with get_conn() as conn:
        entities = [dict(r) for r in conn.execute("SELECT * FROM entities WHERE case_id=?", (case_id,)).fetchall()]
        relationships_raw = conn.execute("SELECT * FROM relationships WHERE case_id=?", (case_id,)).fetchall()
        conflicts_raw = conn.execute("SELECT * FROM conflicts WHERE case_id=?", (case_id,)).fetchall()
        links_raw = conn.execute("SELECT * FROM evidence_links WHERE case_id=?", (case_id,)).fetchall()

    if not entities:
        raise HTTPException(400, "no entities resolved yet — run the analysis first")

    timeline_events = read_timeline(case_id)
    relationships = [{"from": r["from_entity_id"], "to": r["to_entity_id"], "type": r["relationship_type"]} for r in relationships_raw]
    conflicts = [{"claim_a": c["claim_a"], "claim_b": c["claim_b"], "nature_of_conflict": c["nature_of_conflict"] or c["question"]} for c in conflicts_raw]
    evidence_links = [{"claim_a": l["claim_a"], "claim_b": l["claim_b"], "link_type": l["link_type"]} for l in links_raw]

    try:
        result = reconstruct_incident(case_id, timeline_events, entities, relationships, conflicts, evidence_links)
    except Exception as e:  # noqa: BLE001
        raise _server_error("The reconstruction", e)
    from pipeline import sandbox as _sandbox
    try:
        saved = _sandbox.save_narrative(case_id, result, user)
        result = {**result, "narrative_id": saved["narrative_id"]}
    except Exception:  # noqa: BLE001
        _log.exception("could not save the incident narrative")

    _audit(case_id, user, "incident_reconstruction_run", case_id)
    return result


# ------------------------------------------- Scene reconstruction sandbox ----

class GenerateRequest(BaseModel):
    mode: str = "full"  # "full" builds a new scene; "scenarios_only" keeps the current layout


class InterviewRequest(BaseModel):
    hypothesis_text: str = Field(max_length=4000)


class OfficerScenarioRequest(BaseModel):
    hypothesis_text: str = Field(max_length=4000)
    interview: list = Field(default=[], max_length=12)  # [{"question": "...", "answer": "..."}]


class RetractRequest(BaseModel):
    reason: str = Field(max_length=1000)


class LayoutEditRequest(BaseModel):
    ops: list = Field(max_length=60)  # [{"op": "set|add|remove", "kind": "room|fixture|opening|key_location|observer|outdoor_object", "id": "...", "fields": {...}}]


def _sandbox_guard(fn, *args, **kwargs):
    """Maps the sandbox's own errors to clean HTTP statuses and never leaks
    internal exception text for anything unexpected."""
    from pipeline.sandbox import SandboxError
    try:
        return fn(*args, **kwargs)
    except SandboxError as e:
        raise HTTPException(e.status_code, e.message)
    except HTTPException:
        raise
    except Exception:
        log_event(_log, "error", "sandbox endpoint failed", endpoint=getattr(fn, "__name__", "?"))
        _log.exception("sandbox endpoint failed")
        raise HTTPException(500, "The scene service hit an unexpected error. It was logged on the server.")


@app.get("/cases/{case_id}/sandbox")
def sandbox_state(case_id: str, user: dict = Depends(auth.require("view_case"))):
    """Read-only. Returns the saved scene and scenarios; never generates anything."""
    from pipeline import sandbox
    return _sandbox_guard(sandbox.get_state, case_id)


@app.get("/cases/{case_id}/sandbox/runs/{run_id}")
def sandbox_run(case_id: str, run_id: str, user: dict = Depends(auth.require("view_case"))):
    """Any earlier version, read-only (nothing is ever deleted)."""
    from pipeline import sandbox
    return _sandbox_guard(sandbox.get_run, case_id, run_id)


@app.post("/cases/{case_id}/sandbox/generate", status_code=202)
@limiter.limit("5/minute")
def sandbox_generate(request: Request, case_id: str, body: GenerateRequest, background_tasks: BackgroundTasks,
                     user: dict = Depends(auth.require("generate_scenario"))):
    """Starts scene generation in the background and returns at once. Poll GET /sandbox."""
    from pipeline import sandbox
    run_id = _sandbox_guard(sandbox.start_generation, case_id, user, body.mode)
    background_tasks.add_task(sandbox.run_generation, run_id, case_id, user, body.mode)
    return {"run_id": run_id, "status": "generating"}


@app.post("/cases/{case_id}/sandbox/approve-layout")
def sandbox_approve(case_id: str, user: dict = Depends(auth.require("approve_layout"))):
    from pipeline import sandbox
    return _sandbox_guard(sandbox.approve_layout, case_id, user)


@app.post("/cases/{case_id}/sandbox/interview")
@limiter.limit("10/minute")
def sandbox_interview(request: Request, case_id: str, body: InterviewRequest, user: dict = Depends(auth.require("generate_scenario"))):
    from pipeline import sandbox
    questions = _sandbox_guard(sandbox.generate_interview, case_id, body.hypothesis_text, user)
    return {"case_id": case_id, "questions": questions}


@app.post("/cases/{case_id}/sandbox/scenarios")
@limiter.limit("10/minute")
def sandbox_officer_scenario(request: Request, case_id: str, body: OfficerScenarioRequest, user: dict = Depends(auth.require("generate_scenario"))):
    from pipeline import sandbox
    return _sandbox_guard(sandbox.synthesize_custom, case_id, body.hypothesis_text, body.interview, user)


@app.post("/cases/{case_id}/sandbox/scenarios/{scenario_id}/retract")
def sandbox_retract(case_id: str, scenario_id: str, body: RetractRequest, user: dict = Depends(auth.require("generate_scenario"))):
    from pipeline import sandbox
    return _sandbox_guard(sandbox.retract_scenario, case_id, scenario_id, body.reason, user)


@app.post("/cases/{case_id}/sandbox/layout")
@limiter.limit("20/minute")
def sandbox_edit_layout(request: Request, case_id: str, body: LayoutEditRequest, user: dict = Depends(auth.require("generate_scenario"))):
    """Officer measurements and corrections. Builds a new version of the scene (the old one is kept)
    and re-plans every scenario on it without calling a model."""
    from pipeline import sandbox
    return _sandbox_guard(sandbox.apply_layout_edits, case_id, body.ops, user)


@app.post("/cases/{case_id}/sandbox/photo-links")
@limiter.limit("3/minute")
def sandbox_photo_links_create(request: Request, case_id: str, user: dict = Depends(auth.require("generate_scenario"))):
    """Finds the scene's objects in the case photographs (Meta SAM 3.1). Inferred pointers, never proof."""
    from pipeline import sandbox_photos
    return _sandbox_guard(sandbox_photos.create_photo_links, case_id, user)


@app.get("/cases/{case_id}/sandbox/photo-links")
def sandbox_photo_links_get(case_id: str, user: dict = Depends(auth.require("view_case"))):
    _require_case(case_id)
    from pipeline import sandbox_photos
    return _sandbox_guard(sandbox_photos.latest_photo_links, case_id) or {"link_id": None, "content": None}


@app.post("/cases/{case_id}/sandbox/review", status_code=202)
@limiter.limit("2/minute")
def sandbox_review_start(request: Request, case_id: str, background_tasks: BackgroundTasks, user: dict = Depends(auth.require("generate_scenario"))):
    """A second model reviews every scenario against the evidence, the photographs and plan-view pictures of the scene. Runs in the background."""
    from pipeline import sandbox_review
    review_id = _sandbox_guard(sandbox_review.start_review, case_id, user)
    background_tasks.add_task(sandbox_review.run_review, review_id, case_id, user)
    return {"review_id": review_id, "status": "running"}


@app.get("/cases/{case_id}/sandbox/review")
def sandbox_review_get(case_id: str, user: dict = Depends(auth.require("view_case"))):
    _require_case(case_id)
    from pipeline import sandbox_review
    return _sandbox_guard(sandbox_review.latest_review, case_id) or {"review_id": None, "status": "none", "content": None}


@app.get("/cases/{case_id}/sandbox/review/{review_id}/frames/{name}")
def sandbox_review_frame(case_id: str, review_id: str, name: str, user: dict = Depends(auth.require("view_case"))):
    """One plan-view picture the reviewer was shown."""
    from pipeline import sandbox_review
    p = sandbox_review.frame_path(case_id, review_id, name)
    if p is None:
        raise HTTPException(404, "picture not found")
    return FileResponse(p, media_type="image/png")


@app.get("/cases/{case_id}/sandbox/export")
def sandbox_export(case_id: str, user: dict = Depends(auth.require("export_report"))):
    """Review pack: scene, scenarios, citations, raw model calls, audit trail, hashes."""
    from pipeline import sandbox
    return _sandbox_guard(sandbox.export_pack, case_id, user)


@app.get("/cases/{case_id}/sandbox/export.pdf")
def sandbox_export_pdf(case_id: str, user: dict = Depends(auth.require("export_report"))):
    """The same review pack as a printable PDF with floor plans and routes."""
    from pipeline import sandbox
    from pipeline.sandbox_pdf import render_pack_pdf
    pack = _sandbox_guard(sandbox.export_pack, case_id, user)
    return Response(render_pack_pdf(pack), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="CaseWeave_Scene_Review_{case_id}.pdf"'})


@app.get("/cases/{case_id}/narrative")
def get_saved_narrative(case_id: str, user: dict = Depends(auth.require("view_case"))):
    """The latest saved incident narrative (versions are kept)."""
    _require_case(case_id)
    from pipeline import sandbox
    n = _sandbox_guard(sandbox.latest_narrative, case_id)
    return n or {"narrative_id": None, "content": None}


# ----------------------------------------------------------- 4D Incident Simulation ----

@app.get("/cases/{case_id}/simulation")
def get_simulation_endpoint(case_id: str, user: dict = Depends(auth.get_current_user)):
    """Fetch 4D incident simulation data (keyframes, trajectory, spatial telemetry)."""
    from pipeline.simulation import get_case_simulation
    return get_case_simulation(case_id, force_recompute=False)


@app.post("/cases/{case_id}/simulation/generate")
def generate_simulation_endpoint(case_id: str, user: dict = Depends(auth.get_current_user)):
    """Force dynamic regeneration of 4D incident simulation from latest timeline events."""
    from pipeline.simulation import get_case_simulation
    return get_case_simulation(case_id, force_recompute=True)


# ----------------------------------------------------------- Segmentation (Stage 8) ----

class SegmentRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=200)


@app.post("/cases/{case_id}/evidence/{evidence_id}/segment")
@limiter.limit("10/minute")
def segment_evidence(request: Request, case_id: str, evidence_id: str, body: SegmentRequest, user: dict = Depends(auth.require("generate_scenario"))):
    """Stage 8: SAM 3.1 object segmentation on an image evidence item."""
    row = _get_evidence_row(case_id, evidence_id)
    if row.get("evidence_type") != "image":
        raise HTTPException(400, "Segmentation is only supported on image evidence")

    from pipeline.segment import segment_image

    img_path = _intact_path(case_id, row, user)
    try:
        res = segment_image(img_path, body.prompt)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:  # noqa: BLE001
        _log.exception("segmentation failed")
        raise HTTPException(502, "The segmentation service could not process this image. It was logged on the server.")

    _audit(case_id, user, "image_segmented", f"{evidence_id}:{body.prompt}")
    return res


@app.get("/cases/{case_id}/evidence/{evidence_id}/certificate")
def download_evidence_certificate(case_id: str, evidence_id: str, user: dict = Depends(auth.require("export_report"))):
    row = _get_evidence_row(case_id, evidence_id)
    from pipeline.certificate_pdf import generate_evidence_certificate

    # the certificate states that the original is unchanged, so that is checked now, not assumed
    try:
        require_intact(case_id, evidence_id, row["filename"], row["file_hash"])
        integrity = "verified"
    except IntegrityError:
        integrity = "FAILED"
    except FileNotFoundError:
        integrity = "missing"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "certificate.pdf"
        generate_evidence_certificate(case_id, evidence_id, tmp_path, integrity=integrity)
        pdf_bytes = tmp_path.read_bytes()

    _audit(case_id, user, "evidence_certificate_generated", evidence_id)
    return Response(
        pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Draft_Certificate_{evidence_id}.pdf"'},
    )


# --------------------------------------------------------------- Reports ----

def _fresh_report_paths(case_id: str):
    """Rebuilds the reports from the current records (no model call) so they show every review decision made so far."""
    from pipeline.report_refresh import refresh_reports, report_paths
    paths = {k: Path(v) for k, v in report_paths(case_id).items()}
    if not paths["markdown"].exists():
        raise HTTPException(404, "no report generated yet — run the analysis first")
    try:
        refresh_reports(case_id)
    except Exception:  # noqa: BLE001 - fall back to the last saved copy
        _log.exception("report refresh failed; serving the saved copy")
    return paths


@app.get("/cases/{case_id}/report")
def download_report(case_id: str, user: dict = Depends(auth.require("export_report"))):
    _require_case(case_id)
    paths = _fresh_report_paths(case_id)
    _audit(case_id, user, "report_exported", case_id)
    return PlainTextResponse(paths["markdown"].read_text(encoding="utf-8"), media_type="text/markdown")


@app.get("/cases/{case_id}/report/pdf")
def download_report_pdf(case_id: str, user: dict = Depends(auth.require("export_report"))):
    _require_case(case_id)
    paths = _fresh_report_paths(case_id)
    _audit(case_id, user, "pdf_report_exported", case_id)
    return FileResponse(paths["pdf"], media_type="application/pdf", filename=f"CaseWeave_Report_{case_id}.pdf")


@app.get("/health")
def health():
    return {"status": "ok"}


# -------------------------------------------------- Pattern Intelligence ----

@app.get("/cases/{case_id}/patterns")
def get_case_patterns_endpoint(case_id: str, user: dict = Depends(auth.require("view_case"))):
    _require_case(case_id)
    from pipeline.patterns import get_case_patterns
    try:
        return get_case_patterns(case_id)
    except Exception as e:  # noqa: BLE001
        raise _server_error("Pattern intelligence", e)


@app.post("/cases/{case_id}/patterns/extract")
@limiter.limit("5/minute")
def extract_case_patterns_endpoint(request: Request, case_id: str, user: dict = Depends(auth.require("generate_scenario"))):
    _require_case(case_id)
    from pipeline.patterns import get_case_patterns
    try:
        report = get_case_patterns(case_id, force=True)
        return {"status": "extracted", "report": report}
    except Exception as e:  # noqa: BLE001
        raise _server_error("Recomputing pattern intelligence", e)


@app.post("/cases/patterns/seed")
def seed_patterns_endpoint(user: dict = Depends(auth.require("manage_users"))):
    from pipeline.patterns import seed_historical_patterns
    try:
        count = seed_historical_patterns()
        return {"status": "seeded", "count": count, "note": "These are synthetic demonstration records, not real cases."}
    except Exception as e:  # noqa: BLE001
        raise _server_error("Seeding the reference cases", e)


# ---------------------------------------------------- Legal Intelligence ----

@app.get("/legal/search")
def legal_search_endpoint(
    q: str,
    act: Optional[str] = None,
    limit: int = 6,
    user: dict = Depends(auth.require("view_case")),
):
    from pipeline.legal_advisor import universal_legal_search
    if not q.strip() or len(q) > 500:
        raise HTTPException(400, "q must be 1-500 characters")
    try:
        return universal_legal_search(q, top_k=limit, act_filter=act)
    except Exception as e:  # noqa: BLE001
        raise _server_error("Legal search", e)


@app.get("/legal/sections")
def legal_sections_endpoint(user: dict = Depends(auth.require("view_case"))):
    from pipeline.legal_advisor import get_all_legal_corpus_documents
    try:
        return get_all_legal_corpus_documents()
    except Exception as e:  # noqa: BLE001
        raise _server_error("Listing the legal corpus", e)


@app.get("/cases/{case_id}/legal-compliance")
def case_legal_compliance_endpoint(case_id: str, user: dict = Depends(auth.require("view_case"))):
    _require_case(case_id)
    from pipeline.legal_advisor import audit_case_legal_compliance
    try:
        return audit_case_legal_compliance(case_id)
    except Exception as e:  # noqa: BLE001
        raise _server_error("The compliance audit", e)


@app.get("/cases/{case_id}/legal-advisory")
@limiter.limit("10/minute")
def case_legal_advisory_endpoint(request: Request, case_id: str, user: dict = Depends(auth.require("view_case"))):
    _require_case(case_id)
    from pipeline.legal_advisor import get_fir_legal_advisory
    try:
        return get_fir_legal_advisory(case_id)
    except Exception as e:  # noqa: BLE001
        raise _server_error("The FIR advisory", e)
