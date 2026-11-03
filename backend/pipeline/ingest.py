"""Stage 0 — Foundation: register a case, upload/ingest evidence files, hash + store."""
import json
from pathlib import Path

from db import get_conn, file_hash, append_audit_event


def ingest_case(case_id: str, title: str, data_dir: Path):
    conn = get_conn()
    cur = conn.cursor()

    import datetime

    cur.execute(
        "INSERT OR REPLACE INTO cases (case_id, title, created_at) VALUES (?,?,?)",
        (case_id, title, datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()),
    )
    conn.commit()
    append_audit_event(conn, case_id, "system", "case_created", case_id)

    evidence_items = []
    for path in sorted(data_dir.iterdir()):
        if path.name == "ground_truth.json":
            continue  # ground truth is the answer key, not evidence
        if path.suffix == ".json":
            evidence_type = "structured_log"
        elif path.suffix == ".txt":
            evidence_type = "text_document"
        else:
            continue

        evidence_id = f"EV-{case_id}-{path.stem}"
        h = file_hash(path)
        cur.execute(
            "INSERT OR REPLACE INTO evidence_items (evidence_id, case_id, filename, file_hash, evidence_type, status) VALUES (?,?,?,?,?,?)",
            (evidence_id, case_id, path.name, h, evidence_type, "pending"),
        )
        conn.commit()
        append_audit_event(conn, case_id, "system", "evidence_uploaded", evidence_id)

        evidence_items.append(
            {"evidence_id": evidence_id, "path": path, "evidence_type": evidence_type, "hash": h}
        )

    conn.close()
    return evidence_items
