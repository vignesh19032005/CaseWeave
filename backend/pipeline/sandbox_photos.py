"""Links objects in the scene to where they appear in the case's evidence photographs.

Meta's SAM 3.1 outlines objects in a photo from a short noun phrase. We ask it for the
nouns of the objects in the scene (a locker, a counter, a shutter) and keep the boxes it
returns, so an officer can click an object in the scene and see it in the photograph
that supports it. A box is a pointer for the officer to check. It does not prove that
the photographed object is the same object as the one in the scene, and the detector
can miss objects or box the wrong thing, so every link is marked as inferred.
"""
from __future__ import annotations

import datetime
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

from db import get_conn, append_audit_event_txn
from pipeline import sandbox_evidence as evd

logger = logging.getLogger("caseweave.sandbox_photos")

MAX_IMAGES = 6
MAX_TERMS = 8
WORKERS = 4
MIN_AREA_PCT = 1.0   # a box must cover at least 1% of the photograph
MIN_SIDE_PCT = 3.0   # and be at least 3% wide and tall: thinner boxes are slats, edges and noise
MAX_PER_TERM = 3     # the largest few per word and photograph

_VEHICLE_WORDS = ("motorcycle", "motorbike", "scooter", "bike", "van", "car", "truck", "lorry", "bus", "auto", "jeep", "tempo")


def keep_boxes(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The detector returns no confidence, so only plausible-sized boxes are kept, largest first."""
    good = []
    for m in matches:
        b = m.get("box") or {}
        w, h = b.get("pct_width", 0), b.get("pct_height", 0)
        if w >= MIN_SIDE_PCT and h >= MIN_SIDE_PCT and (w * h) / 100.0 >= MIN_AREA_PCT:
            good.append(m)
    good.sort(key=lambda m: m["box"]["pct_width"] * m["box"]["pct_height"], reverse=True)
    return good[:MAX_PER_TERM]

_CATEGORY_NOUN = {"counter": "counter", "shelf": "shelf", "cabinet": "cabinet", "safe": "safe", "locker": "locker", "table": "table",
                  "desk": "desk", "chair": "chair", "bed": "bed", "appliance": "machine"}


def _two_words(label: str) -> str:
    words = [w for w in "".join(c if c.isalnum() or c == " " else " " for c in (label or "")).lower().split() if len(w) > 2]
    return " ".join(words[-2:]) if words else ""


def term_for_fixture(f: Dict[str, Any]) -> str:
    lab = (f.get("label") or "").lower()
    for key, noun in (("locker", "locker"), ("cabinet", "cabinet"), ("safe", "safe"), ("shutter", "shutter"), ("counter", "counter"), ("shelf", "shelf"), ("shelv", "shelf"),
                      ("drawer", "drawer"), ("crowbar", "crowbar"), ("glove", "glove"), ("table", "table"), ("desk", "desk"), ("bed", "bed"), ("sofa", "sofa")):
        if key in lab:
            return noun
    return _CATEGORY_NOUN.get((f.get("category") or "").lower()) or _two_words(f.get("label") or "")


def term_for_opening(o: Dict[str, Any]) -> str:
    lab = (o.get("label") or "").lower()
    for key in ("shutter", "gate", "window", "door"):
        if key in lab:
            return key
    return "door"


def terms_for_layout(layout: Dict[str, Any]) -> List[Dict[str, str]]:
    """One search phrase per object, capped; objects sharing a phrase share the detection."""
    out: List[Dict[str, str]] = []
    seen = set()
    sources: List[Tuple[str, str, str]] = []
    for o in layout.get("openings", []):
        if o.get("kind") == "external":
            sources.append(("opening", o["id"], term_for_opening(o)))
    for f in layout.get("fixtures", []):
        sources.append(("fixture", f["id"], term_for_fixture(f)))
    for ob in layout.get("outdoor_objects", []):
        label_words = (ob.get("label") or "").lower().split()
        cleaned = [w.strip("(),.") for w in label_words]
        noun = next((w if w in _VEHICLE_WORDS else w[:-1] for w in cleaned if w in _VEHICLE_WORDS or w[:-1] in _VEHICLE_WORDS), None)
        if noun:  # only things a detector can be asked about by a plain noun
            sources.append(("outdoor_object", ob["id"], noun))
    labels = {n["id"]: n.get("label", n["id"]) for g in ("openings", "fixtures", "outdoor_objects") for n in layout.get(g, [])}
    for kind, nid, term in sources:
        term = (term or "").strip()
        if not term or term in seen:
            continue
        seen.add(term)
        out.append({"node_id": nid, "node_kind": kind, "label": labels.get(nid, nid), "term": term})
        if len(out) >= MAX_TERMS:
            break
    return out


def link_photos(photo_paths: List[Dict[str, Any]], terms: List[Dict[str, str]], segment: Callable[[Any, str], Dict[str, Any]]) -> Dict[str, Any]:
    """photo_paths: [{evidence_id, filename, path}]. Runs the detector over every photo and term."""
    jobs = [(p, t) for p in photo_paths for t in terms]
    results: Dict[Tuple[str, str], Optional[Dict[str, Any]]] = {}
    errors = 0

    def run(job):
        p, t = job
        try:
            return (p["evidence_id"], t["term"]), segment(p["path"], t["term"])
        except Exception as e:  # noqa: BLE001 - one failed call must not lose the others; counted below
            logger.info("photo detection failed for %s / %s: %s", p["evidence_id"], t["term"], str(e)[:120])
            return (p["evidence_id"], t["term"]), None

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for key, res in pool.map(run, jobs):
            results[key] = res
            if res is None:
                errors += 1
    photos: List[Dict[str, Any]] = []
    for p in photo_paths:
        matches: List[Dict[str, Any]] = []
        w = h = None
        for t in terms:
            res = results.get((p["evidence_id"], t["term"]))
            for m in keep_boxes((res or {}).get("matches", [])):
                b = m["box"]
                w, h = b.get("image_width", w), b.get("image_height", h)
                matches.append({"node_id": t["node_id"], "node_kind": t["node_kind"], "label": t["label"], "term": t["term"],
                                "pct": [b["pct_left"], b["pct_top"], b["pct_width"], b["pct_height"]]})
        photos.append({"evidence_id": p["evidence_id"], "filename": p["filename"], "image_width": w, "image_height": h, "matches": matches})
    return {
        "photos": photos, "terms": terms, "calls": len(jobs), "calls_failed": errors,
        "detector": "SAM 3.1 (Meta, hosted)", "basis": "inferred",
        "caveat": "A box shows where the detector found an object matching the word. It can miss objects or box the wrong one, and it does not prove the photographed object is the one in the scene.",
    }


def _now() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def create_photo_links(case_id: str, user: Dict[str, Any], segment: Optional[Callable] = None) -> Dict[str, Any]:
    from pipeline.sandbox import SandboxError, _current_ready_run, _audit_in_txn
    from storage import get_object_path
    conn = get_conn()
    try:
        run = _current_ready_run(conn, case_id)
    finally:
        conn.close()
    layout = json.loads(run["layout_json"])
    ev = evd.gather_evidence(case_id)
    images = [e for e in ev["evidence_items"] if e.get("evidence_type") == "image"][:MAX_IMAGES]
    if not images:
        raise SandboxError("This case has no photographs to link objects to.")
    terms = terms_for_layout(layout)
    if not terms:
        raise SandboxError("The scene has no objects to look for in the photographs.")
    if segment is None:
        from pipeline.segment import _segment_single as segment  # noqa: PLW0127
    paths = [{"evidence_id": e["evidence_id"], "filename": e["filename"], "path": get_object_path(case_id, e["evidence_id"], e["filename"])} for e in images]
    content = link_photos(paths, terms, segment)
    if content["calls"] and content["calls_failed"] == content["calls"]:
        raise SandboxError("The object detector could not be reached. Nothing was saved. Try again shortly.")
    content["run_id"] = run["run_id"]
    content["layout_hash"] = run["layout_hash"]
    content_hash = evd.canonical_hash(content)
    link_id = f"PHL-{uuid.uuid4().hex[:12]}"
    conn = get_conn()
    release = None
    try:
        conn.execute("INSERT INTO sandbox_photo_links (link_id, case_id, run_id, layout_hash, content_json, content_hash, created_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (link_id, case_id, run["run_id"], run["layout_hash"], json.dumps(content), content_hash, user.get("username", "system"), _now()))
        _, release = _audit_in_txn(conn, case_id, user, "sandbox_photo_links_created", f"{link_id}:{content_hash[:16]}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if release:
            release()
        conn.close()
    return {"link_id": link_id, "content_hash": content_hash, "created_by": user.get("username", "system"), "content": content}


def latest_photo_links(case_id: str) -> Optional[Dict[str, Any]]:
    """The newest links, only if they belong to the scene version currently shown."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM sandbox_photo_links WHERE case_id=? ORDER BY created_at DESC LIMIT 1", (case_id,)).fetchone()
        cur = conn.execute("SELECT run_id, layout_hash FROM sandbox_runs WHERE case_id=? AND is_current=1 AND status='ready'", (case_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    content = json.loads(row["content_json"])
    stale = not cur or cur["layout_hash"] != row["layout_hash"]
    return {"link_id": row["link_id"], "created_by": row["created_by"], "created_at": row["created_at"], "content_hash": row["content_hash"], "stale": stale, "content": content}
