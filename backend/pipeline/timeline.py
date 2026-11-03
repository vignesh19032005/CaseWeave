"""Stage 3 — Timeline Builder: order observations with a known time into a chronological view.

Times are clock times without a date. They are ordered with pipeline.timeutil so that an incident straddling
midnight reads in the right order and a "9:10 PM" never sorts after "10:00"."""
import uuid

from db import get_conn, append_audit_event
from pipeline.timeutil import normalize_clock, sort_chronologically


def build_timeline(case_id: str):
    conn = get_conn()
    cur = conn.cursor()
    # Rebuild from scratch each call so re-running the pipeline doesn't pile
    # duplicate events on top of a prior run's timeline.
    cur.execute("DELETE FROM timeline_events WHERE case_id=?", (case_id,))
    cur.execute(
        "SELECT * FROM observations WHERE case_id=? AND extracted_time IS NOT NULL",
        (case_id,),
    )
    rows = []
    for row in cur.fetchall():
        clock = normalize_clock(row["extracted_time"])  # also repairs rows written before times were validated
        if clock:
            rows.append({**row, "extracted_time": clock})
    rows = sort_chronologically(rows, key="extracted_time")

    events = []
    for row in rows:
        event_id = f"EVT-{uuid.uuid4().hex[:8]}"
        cur.execute(
            "INSERT INTO timeline_events (event_id, case_id, event_time, description, source_observation_id) VALUES (?,?,?,?,?)",
            (event_id, case_id, row["extracted_time"], row["description"], row["observation_id"]),
        )
        events.append(
            {
                "event_id": event_id,
                "time": row["extracted_time"],
                "description": row["description"],
                "source_observation_id": row["observation_id"],
                "source_evidence_id": row["source_evidence_id"],
                "classification": row["classification"],
            }
        )
    conn.commit()
    append_audit_event(conn, case_id, "system", "timeline_built", case_id)
    conn.close()
    return events


def get_timeline(case_id: str):
    """Read-only view of the timeline the last pipeline run built. GET
    endpoints must use this, not build_timeline — rebuilding on every read
    regenerated event IDs and appended an audit event per page load, and two
    concurrent loads forked the audit hash chain."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT t.event_id, t.event_time, t.description, t.source_observation_id,
                  o.source_evidence_id, o.classification
           FROM timeline_events t
           LEFT JOIN observations o ON o.observation_id = t.source_observation_id
           WHERE t.case_id=?""",
        (case_id,),
    ).fetchall()
    conn.close()
    events = [
        {
            "event_id": r["event_id"],
            "time": r["event_time"],
            "description": r["description"],
            "source_observation_id": r["source_observation_id"],
            "source_evidence_id": r["source_evidence_id"],
            "classification": r["classification"] or "unknown",
        }
        for r in rows
    ]
    return sort_chronologically(events, key="time")
