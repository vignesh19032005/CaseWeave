"""Stage 10 — Report Export + Audit Trail. Produces a Markdown report, the Stage-10 deliverable."""
import datetime
from pathlib import Path

from db import get_conn, verify_audit_chain


def generate_report(case_id: str, timeline_events, conflicts, scenarios, legal_results, out_path: Path, reconstruction: dict | None = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cases WHERE case_id=?", (case_id,))
    case = cur.fetchone()
    cur.execute("SELECT * FROM evidence_items WHERE case_id=?", (case_id,))
    evidence = cur.fetchall()
    cur.execute("SELECT * FROM observations WHERE case_id=?", (case_id,))
    observations = cur.fetchall()
    cur.execute("SELECT COUNT(*) as n FROM audit_events WHERE case_id=?", (case_id,))
    audit_count = cur.fetchone()["n"]
    chain_ok = verify_audit_chain(conn, case_id)
    conn.close()

    lines = []
    lines.append(f"# CaseWeave Report — {case['title']} ({case_id})\n")
    lines.append(f"Generated: {datetime.datetime.utcnow().isoformat(timespec='seconds')}Z\n")

    lines.append("## 1. Case Overview\n")
    lines.append(f"Case ID: {case_id}")
    lines.append(f"Case opened: {case['created_at']}")
    lines.append(f"Evidence items: {len(evidence)} · Observations: {len(observations)} · "
                 f"Timeline events: {len(timeline_events)} · Conflicts: {len(conflicts)}\n")

    lines.append("## 2. Evidence Inventory\n")
    for e in evidence:
        lines.append(f"- `{e['evidence_id']}` — {e['filename']} (type: {e['evidence_type']}, sha256: {e['file_hash'][:16]}...)")
    lines.append("")

    lines.append("## 3. Evidence-Linked Chronology\n")
    for ev in timeline_events:
        lines.append(f"- **{ev['time']}** [{ev['classification']}] {ev['description']} — source: `{ev['source_evidence_id']}`")
    lines.append("")

    lines.append("## 4. Findings and Unresolved Discrepancies\n")
    if conflicts:
        for c in conflicts:
            lines.append(f"### {c['conflict_id']}")
            lines.append(f"- Claim A ({c['time_a']}, `{c['source_a']}`): {c['claim_a']}")
            lines.append(f"- Claim B ({c['time_b']}, `{c['source_b']}`): {c['claim_b']}")
            lines.append(f"- Nature of conflict: {c.get('nature_of_conflict', '')}")
            lines.append(f"- Verification question: {c['question']}\n")
    else:
        lines.append("No discrepancies detected.\n")

    lines.append("## 5. Competing Scenarios\n")
    if not scenarios:
        lines.append("No competing scenarios generated (no conflicts detected).\n")
    for s in scenarios:
        lines.append(f"### {s.get('name', 'Unnamed scenario')}")
        lines.append(f"- Assumption: {s.get('assumption', '—')}")
        lines.append(f"- Supporting: {s.get('supporting_evidence', '—')}")
        lines.append(f"- Challenging: {s.get('challenging_evidence', '—')}\n")

    lines.append("## 6. Missing Evidence / Recommended Verification Steps\n")
    steps = [c["question"] for c in conflicts if c.get("question")]
    if steps:
        for q in dict.fromkeys(steps):  # dedupe, keep order
            lines.append(f"- {q}")
    else:
        lines.append("- No open verification steps were generated from conflicts.")
    lines.append("")

    lines.append("## 6a. Unresolved Gaps — Best Guess, Not a Finding\n")
    gaps = (reconstruction or {}).get("unresolved_gaps") or []
    if gaps:
        lines.append(
            "Each gap below is a specific open question the evidence does not resolve. Where a best guess is "
            "given, it is the AI's inference from the AVAILABLE evidence only — it is **not** a conclusion, "
            "has **not** been independently verified, and must be checked before being relied on.\n"
        )
        for g in gaps:
            lines.append(f"- **{g['question']}**")
            if g.get("best_guess"):
                lines.append(f"  - Possible answer (unverified, confidence: {g.get('confidence', 'none')}): {g['best_guess']}")
                if g.get("basis"):
                    lines.append(f"  - Basis: {g['basis']}")
            else:
                lines.append("  - No basis in the evidence for even a tentative guess.")
    else:
        lines.append("- No reconstruction-level gaps generated (reconstruction not run for this report).")
    lines.append("")

    lines.append("## 7. Relevant Legal Authorities\n")
    for r in legal_results:
        lines.append(f"- **{r['title']}** (similarity: {r['similarity_score']})")
        lines.append(f"  > {r['passage'][:300]}...")
        if r.get("source_url"):
            lines.append(f"  Source: {r['source_url']}")
    lines.append("")

    lines.append("## 8. Audit Trail\n")
    lines.append(f"- Total audit events logged: {audit_count}")
    lines.append(f"- Hash-chain integrity check: {'PASSED' if chain_ok else 'FAILED'}\n")

    lines.append("## 9. Pilot Readiness Gap\n")
    lines.append("AI stages (observation extraction, discrepancy debate, scenario generation) ran as live "
                  "LLM calls via the Meta -> Groq -> Gemini fallback chain in backend/llm_client.py — the "
                  "audit log records which provider answered. All AI output is investigative support, not "
                  "a finding: every conflict and claim above must be verified against its cited source. "
                  "Before any live case: security hardening, legal sign-off on schema, and real-casework "
                  "validation are still required. See PLAN.md 'Pilot Readiness Gap & Next Steps'.\n")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
