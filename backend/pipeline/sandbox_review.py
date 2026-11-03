"""Runs the reviewer model over the current scenarios of a case, in the background, and keeps the result.

A review is stored like everything else: attributable, hashed, audited, and tied to the scene version it looked at. The
plan-view pictures it used are kept on disk so a person can see exactly what the reviewer saw.
"""
from __future__ import annotations

import datetime
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from db import get_conn
from llm_client import LLMUnavailableError, _parse_json_text, active_providers, chat_json_ex, chat_vision_multi, model_id, provider_mode
from pipeline import sandbox_evidence as evd
from pipeline import sandbox_reviewer as rv
from pipeline.redaction import build_redactor, redaction_enabled
from storage import STORE_ROOT, get_object_path

logger = logging.getLogger("caseweave.sandbox_review")
FRAME_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}_F\d{1,3}\.png$")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec="microseconds") + "Z"


def frames_dir(case_id: str, review_id: str) -> Path:
    return STORE_ROOT / case_id / "review_frames" / review_id


def start_review(case_id: str, user: Dict[str, Any]) -> str:
    from pipeline.sandbox import SandboxError, _current_ready_run, _audit_in_txn
    conn = get_conn()
    release = None
    try:
        run = _current_ready_run(conn, case_id)
        busy = conn.execute("SELECT review_id, created_at FROM sandbox_reviews WHERE case_id=? AND status='running' ORDER BY created_at DESC LIMIT 1", (case_id,)).fetchone()
        if busy:
            age = (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.datetime.fromisoformat(busy["created_at"].rstrip("Z"))).total_seconds()
            if age < 900:
                raise SandboxError("A review of this scene is already running.", 409)
            conn.execute("UPDATE sandbox_reviews SET status='failed', message='timed out' WHERE review_id=?", (busy["review_id"],))
        review_id = f"REV-{uuid.uuid4().hex[:12]}"
        conn.execute("INSERT INTO sandbox_reviews (review_id, case_id, run_id, layout_hash, status, message, content_json, content_hash, created_by, created_at, completed_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (review_id, case_id, run["run_id"], run["layout_hash"], "running", "", None, None, user.get("username", "system"), _now(), None))
        _, release = _audit_in_txn(conn, case_id, user, "sandbox_review_started", review_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if release:
            release()
        conn.close()
    return review_id


def _photos(case_id: str, ev: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for e in ev["evidence_items"]:
        if e.get("evidence_type") != "image":
            continue
        desc = next((o.get("description") or "" for o in ev["observations"] if o.get("source_evidence_id") == e["evidence_id"]), "")
        try:
            path = get_object_path(case_id, e["evidence_id"], e["filename"])
        except Exception:  # noqa: BLE001 - a missing file just means one photo fewer
            continue
        out.append({"path": path, "caption": f"{e['filename']} [{e['evidence_id']}]" + (f": {desc[:200]}" if desc else "")})
    return out


def vision_available() -> bool:
    return "meta" in {n for n, _ in active_providers()}


def make_call(redactor) -> Callable:
    def call(system: str, text: str, images: List[Any]) -> Dict[str, Any]:
        if images:
            provider, raw = chat_vision_multi(system, text, images, 4096, 240)
            return {"provider": provider, "model": model_id(provider), "parsed": redactor.restore_json(_parse_json_text(provider, raw))}
        res = chat_json_ex(system, text, 4096, 240)
        return {"provider": res["provider"], "model": res["model"], "parsed": redactor.restore_json(res["parsed"])}
    return call


def run_review(review_id: str, case_id: str, user: Dict[str, Any], call: Optional[Callable] = None, with_images: Optional[bool] = None) -> None:
    from pipeline.sandbox import _audit_in_txn, _current_ready_run
    try:
        conn = get_conn()
        try:
            run = _current_ready_run(conn, case_id)
            rows = [dict(r) for r in conn.execute("SELECT content_json FROM sandbox_scenarios WHERE run_id=? AND status='active' ORDER BY rank_order", (run["run_id"],)).fetchall()]
        finally:
            conn.close()
        layout = json.loads(run["layout_json"])
        scenarios = [json.loads(r["content_json"]) for r in rows]
        ev = evd.gather_evidence(case_id)
        redactor = build_redactor(ev["entities"], redaction_enabled())
        known = evd.known_refs(ev)
        photos = _photos(case_id, ev)
        use_images = vision_available() if with_images is None else with_images
        call = call or make_call(redactor)
        out_dir = frames_dir(case_id, review_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        results = []
        for scn in scenarios:
            def on_frame(fid: str, png: bytes, sid: str = scn["scenario_id"]) -> None:
                (out_dir / f"{sid}_{fid}.png").write_bytes(png)
            res = rv.review_scenario(scn, layout, ev, known, photos, call, redact=redactor.redact, with_images=use_images, on_frame=on_frame)
            res["frame_files"] = {f["id"]: f"{scn['scenario_id']}_{f['id']}.png" for f in res["frames"]}
            results.append(res)
        content = {"run_id": run["run_id"], "layout_hash": run["layout_hash"], "provider_mode": provider_mode(), "scenarios": results,
                   "reviewed_with_images": any(r["reviewed_with_images"] for r in results)}
        h = evd.canonical_hash(content)
        conn = get_conn()
        release = None
        try:
            conn.execute("UPDATE sandbox_reviews SET status='done', content_json=?, content_hash=?, completed_at=? WHERE review_id=?", (json.dumps(content), h, _now(), review_id))
            _, release = _audit_in_txn(conn, case_id, user, "sandbox_review_completed", f"{review_id}:{h[:16]}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if release:
                release()
            conn.close()
    except Exception as e:  # noqa: BLE001 - a background job records any failure instead of dying silently
        logger.exception("review %s failed", review_id)
        msg = "The review could not be completed." if not isinstance(e, LLMUnavailableError) else "The reviewer model could not be reached."
        conn = get_conn()
        try:
            conn.execute("UPDATE sandbox_reviews SET status='failed', message=?, completed_at=? WHERE review_id=?", (msg, _now(), review_id))
            conn.commit()
        finally:
            conn.close()


def latest_review(case_id: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM sandbox_reviews WHERE case_id=? ORDER BY created_at DESC LIMIT 1", (case_id,)).fetchone()
        cur = conn.execute("SELECT run_id, layout_hash FROM sandbox_runs WHERE case_id=? AND is_current=1 AND status='ready'", (case_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    content = json.loads(row["content_json"]) if row["content_json"] else None
    return {"review_id": row["review_id"], "status": row["status"], "message": row["message"], "created_by": row["created_by"], "created_at": row["created_at"],
            "completed_at": row["completed_at"], "content_hash": row["content_hash"], "stale": bool(cur and row["run_id"] != cur["run_id"]), "content": content}


def frame_path(case_id: str, review_id: str, name: str) -> Optional[Path]:
    if not FRAME_NAME_RE.match(name):
        return None
    conn = get_conn()
    try:
        ok = conn.execute("SELECT 1 FROM sandbox_reviews WHERE review_id=? AND case_id=?", (review_id, case_id)).fetchone()
    finally:
        conn.close()
    p = frames_dir(case_id, review_id) / name
    return p if ok and p.is_file() else None
