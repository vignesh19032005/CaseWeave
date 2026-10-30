"""Stage 3 — Timeline Builder: order observations with a known time into a chronological view."""
import uuid

from db import get_conn, append_audit_event


def build_timeline(case_id: str):
    conn = get_conn()
    cur = conn.cursor()
    # Rebuild from scratch each call so re-running the pipeline doesn't pile
    # duplicate events on top of a prior run's timeline.
    cur.execute("DELETE FROM timeline_events WHERE case_id=?", (case_id,))
    cur.execute(
        "SELECT * FROM observations WHERE case_id=? AND extracted_time IS NOT NULL ORDER BY extracted_time ASC",
        (case_id,),
    )
    rows = cur.fetchall()

    events = []
    for row in rows:
        event_id = f"EVT-{uuid.uuid4().hex[:8]}"
        cur.execute(
            "INSERT INTO timeline_events VALUES (?,?,?,?,?)",
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
           WHERE t.case_id=? ORDER BY t.event_time ASC""",
        (case_id,),
    ).fetchall()
    conn.close()
    return [
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
