"""Rebuilds a case's reports from what is stored, without calling any model.

The reports used to be written once, at the end of a processing run, so a reviewer who later confirmed or
resolved a conflict never saw that decision in the exported report. This module regenerates the Markdown report,
the PDF and the timeline page from the database (timeline, conflicts with their review status and latest review
note, audit trail) plus the run-specific material saved by the job (scenarios, legal authorities, narrative).
It is called at the end of a run and again whenever a conflict is reviewed.
"""
import json
from pathlib import Path

from db import get_conn
from pipeline.report import generate_report
from pipeline.report_pdf import generate_report_pdf
from pipeline.timeline import get_timeline
from pipeline.timeline_html import render_timeline_html

BACKEND_DIR = Path(__file__).parent.parent
REPORT_DATA_DIR = BACKEND_DIR / "report_data"


def report_paths(case_id: str) -> dict:
    return {
        "markdown": str(BACKEND_DIR / f"output_report_{case_id}.md"),
        "pdf": str(BACKEND_DIR / f"output_report_{case_id}.pdf"),
        "timeline_html": str(BACKEND_DIR / f"timeline_{case_id}.html"),
    }


def _conflicts_with_reviews(case_id: str) -> list:
    out = []
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM conflicts WHERE case_id=?", (case_id,)).fetchall()
        for r in rows:
            last = conn.execute(
                "SELECT status, reason, actor_username, timestamp FROM conflict_reviews WHERE case_id=? AND conflict_id=? ORDER BY timestamp DESC LIMIT 1",
                (case_id, r["conflict_id"]),
            ).fetchone()
            d = {k: r[k] for k in ("conflict_id", "claim_a", "source_a", "time_a", "claim_b", "source_b", "time_b", "question", "nature_of_conflict")}
            d["question"] = d["question"] or ""
            d["review_status"] = r["review_status"] or "unresolved"
            if last and last["status"] != "unresolved":
                d["review_note"] = f"{last['reason']} ({last['actor_username']}, {last['timestamp']})"
            out.append(d)
    return out


def refresh_reports(case_id: str) -> dict:
    """Regenerates all three report files and returns their paths."""
    saved = {}
    data_file = REPORT_DATA_DIR / f"{case_id}.json"
    if data_file.exists():
        try:
            saved = json.loads(data_file.read_text(encoding="utf-8"))
        except ValueError:
            saved = {}
    with get_conn() as conn:
        case = conn.execute("SELECT title FROM cases WHERE case_id=?", (case_id,)).fetchone()
    if not case:
        raise ValueError(f"case not found: {case_id}")

    paths = report_paths(case_id)
    timeline = get_timeline(case_id)
    conflicts = _conflicts_with_reviews(case_id)
    scenarios = saved.get("scenarios") or []
    legal_results = saved.get("legal_results") or []
    reconstruction = saved.get("reconstruction")

    generate_report(case_id, timeline, conflicts, scenarios, legal_results, Path(paths["markdown"]), reconstruction)
    generate_report_pdf(case_id, timeline, conflicts, scenarios, legal_results, Path(paths["pdf"]), reconstruction)
    render_timeline_html(case_id, case["title"], timeline, conflicts, Path(paths["timeline_html"]))
    return paths


def delete_report_files(case_id: str) -> None:
    for p in list(report_paths(case_id).values()) + [str(REPORT_DATA_DIR / f"{case_id}.json")]:
        Path(p).unlink(missing_ok=True)
