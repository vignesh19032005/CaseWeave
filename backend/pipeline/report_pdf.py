"""
Stage 10 (PDF variant) — same content as pipeline/report.py's Markdown
report, typeset as a real formatted PDF via reportlab: headings, bordered
tables for evidence/conflicts, color-coded sections. Not an HTML->PDF
conversion of the Markdown — built directly from the same source data so
both outputs can't drift apart in content, only in presentation.
"""
import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak,
)

from db import get_conn, verify_audit_chain, verify_audit_chain_detail
from pipeline.pdf_fonts import FONT, FONT_BOLD, fit

NAVY = colors.HexColor("#1e3a5f")
AMBER = colors.HexColor("#92620a")
RED = colors.HexColor("#7f1d1d")
GREEN = colors.HexColor("#14532d")
GREY = colors.HexColor("#52525b")
LIGHT_GREY = colors.HexColor("#f4f4f5")

_styles = getSampleStyleSheet()
for _name in ("Title", "Normal", "Heading2", "Heading3"):
    _styles[_name].fontName = FONT_BOLD if _name != "Normal" else FONT
_styles.add(ParagraphStyle("CWTitle", parent=_styles["Title"], textColor=NAVY, fontSize=18, leading=22, spaceAfter=4))
_styles.add(ParagraphStyle("CWMeta", parent=_styles["Normal"], textColor=GREY, fontSize=10, leading=14, spaceAfter=8))
_styles.add(ParagraphStyle("CWH2", parent=_styles["Heading2"], textColor=NAVY, fontSize=12.5, leading=16, spaceBefore=16, spaceAfter=8,
                           borderPadding=(0, 0, 4, 0)))
_styles.add(ParagraphStyle("CWH3", parent=_styles["Heading3"], textColor=colors.HexColor("#27272a"),
                           spaceBefore=10, spaceAfter=4, fontSize=11, leading=14))
_styles.add(ParagraphStyle("CWBody", parent=_styles["Normal"], fontSize=10, leading=15, alignment=TA_LEFT))
_styles.add(ParagraphStyle("CWSmall", parent=_styles["Normal"], fontSize=8.5, leading=12, textColor=GREY))
_styles.add(ParagraphStyle("CWWarn", parent=_styles["Normal"], fontSize=9, leading=13, textColor=AMBER))
_styles.add(ParagraphStyle("CWCell", parent=_styles["Normal"], fontSize=8.5, leading=11, alignment=TA_LEFT))
_styles.add(ParagraphStyle("CWCellHeader", parent=_styles["Normal"], fontSize=9, leading=12, textColor=colors.white, fontName=FONT_BOLD))


def esc(text) -> str:
    """Escapes a single DATA value (evidence text, titles, LLM output) for
    safe interpolation into a Paragraph's mini-HTML. Every data value that
    goes into _p()'s template must be wrapped in this — _p() itself does
    NOT escape, so the <b>/<br/> markup this module writes intentionally
    still renders instead of showing up as literal tags."""
    return fit(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _p(markup: str, style: str = "CWBody") -> Paragraph:
    """markup is trusted template text (may contain intentional <b>, <br/>,
    &middot; etc.) with any data values already passed through esc()."""
    return Paragraph(markup, _styles[style])


def _section_rule(color=NAVY):
    return HRFlowable(width="100%", thickness=1.2, color=color, spaceAfter=10)


def generate_report_pdf(case_id: str, timeline_events, conflicts, scenarios, legal_results, out_path: Path, reconstruction: dict | None = None):
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

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"CaseWeave Report — {case['title']}",
    )
    story = []

    story.append(_p(f"CaseWeave Investigation Report", "CWTitle"))
    story.append(_p(f"{esc(case['title'])} &middot; {esc(case_id)}", "CWMeta"))
    story.append(_p(f"Generated {datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).strftime('%d %b %Y, %H:%M UTC')}", "CWSmall"))
    story.append(Spacer(1, 6))
    story.append(_section_rule())

    # --- 1. Overview ---
    story.append(_p("1. Case Overview", "CWH2"))
    overview_rows = [
        [_p("<b>Case opened</b>", "CWBody"), _p(case["created_at"][:19].replace("T", " "), "CWBody")],
        [_p("<b>Evidence items</b>", "CWBody"), _p(str(len(evidence)), "CWBody")],
        [_p("<b>Observations extracted</b>", "CWBody"), _p(str(len(observations)), "CWBody")],
        [_p("<b>Timeline events</b>", "CWBody"), _p(str(len(timeline_events)), "CWBody")],
        [_p("<b>Conflicts detected</b>", "CWBody"), _p(str(len(conflicts)), "CWBody")],
    ]
    t = Table(overview_rows, colWidths=[60 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e4e4e7")),
    ]))
    story.append(t)

    # --- 2. Evidence inventory ---
    story.append(_p("2. Evidence Inventory", "CWH2"))
    rows = [[
        _p("ID", "CWCellHeader"),
        _p("Filename", "CWCellHeader"),
        _p("Type", "CWCellHeader"),
        _p("SHA-256", "CWCellHeader"),
    ]]
    for e in evidence:
        rows.append([
            _p(f"<font size=7.5>{esc(e['evidence_id'])}</font>", "CWCell"),
            _p(esc(e["filename"]), "CWCell"),
            _p(esc(e["evidence_type"]), "CWCell"),
            _p(f"<font size=7.5>{esc(e['file_hash'][:18])}...</font>", "CWCell"),
        ])
    ev_table = Table(rows, colWidths=[36 * mm, 64 * mm, 32 * mm, 48 * mm], repeatRows=1)
    ev_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d4d4d8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(ev_table)

    # --- 3. Timeline ---
    story.append(_p("3. Evidence-Linked Chronology", "CWH2"))
    rows = [[
        _p("Time", "CWCellHeader"),
        _p("Class", "CWCellHeader"),
        _p("Description", "CWCellHeader"),
        _p("Source", "CWCellHeader"),
    ]]
    for ev in timeline_events:
        time_val = ev.get("time") or ev.get("event_time") or "—"
        class_val = ev.get("classification") or "observed"
        source_val = ev.get("source_evidence_id") or ev.get("source_observation_id") or "—"
        rows.append([
            _p(esc(time_val), "CWCell"),
            _p(esc(class_val), "CWCell"),
            _p(esc(ev.get("description", "")), "CWCell"),
            _p(f"<font size=7>{esc(source_val)}</font>", "CWCell"),
        ])
    tl_table = Table(rows, colWidths=[18 * mm, 20 * mm, 98 * mm, 44 * mm], repeatRows=1)
    tl_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d4d4d8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tl_table)
    story.append(PageBreak())

    # --- 4. Conflicts ---
    story.append(_p("4. Findings and Unresolved Discrepancies", "CWH2"))
    if conflicts:
        for c in conflicts:
            story.append(_p(esc(c["conflict_id"]), "CWH3"))
            box = Table(
                [[_p(f"<b>Claim A</b> ({esc(c['time_a'])}, {esc(c['source_a'])})<br/>{esc(c['claim_a'])}", "CWBody")],
                 [_p(f"<b>Claim B</b> ({esc(c['time_b'])}, {esc(c['source_b'])})<br/>{esc(c['claim_b'])}", "CWBody")],
                 [_p(f"<b>Nature of conflict:</b> {esc(c.get('nature_of_conflict', ''))}", "CWBody")],
                 [_p(f"<b>Recommended next step:</b> {esc(c['question'])}", "CWWarn")],
                 [_p(f"<b>Review status:</b> {esc(c.get('review_status') or 'unresolved')}" + (f" — {esc(c['review_note'])}" if c.get('review_note') else ""), "CWBody")]],
                colWidths=[180 * mm],
            )
            box.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.8, RED),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#fecaca")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef2f2")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(box)
            story.append(Spacer(1, 8))
    else:
        story.append(_p("No discrepancies detected.", "CWBody"))

    # --- 5. Scenarios ---
    story.append(_p("5. Competing Scenarios", "CWH2"))
    if scenarios:
        for s in scenarios:
            story.append(_p(esc(s.get("name", "Unnamed scenario")), "CWH3"))
            story.append(_p(f"<b>Assumption:</b> {esc(s.get('assumption', '—'))}", "CWBody"))
            story.append(_p(f"<b>Supporting:</b> {esc(s.get('supporting_evidence', '—'))}", "CWBody"))
            story.append(_p(f"<b>Challenging:</b> {esc(s.get('challenging_evidence', '—'))}", "CWBody"))
            story.append(Spacer(1, 6))
    else:
        story.append(_p("No competing scenarios generated (no conflicts detected).", "CWBody"))

    # --- 6. Recommended verification steps ---
    story.append(_p("6. Recommended Verification Steps", "CWH2"))
    steps = list(dict.fromkeys(c["question"] for c in conflicts if c.get("question")))
    if steps:
        for q in steps:
            story.append(_p(f"&bull; {esc(q)}", "CWBody"))
    else:
        story.append(_p("No open verification steps were generated from conflicts.", "CWBody"))

    # --- 6a. Unresolved gaps with confidence ---
    gaps = (reconstruction or {}).get("unresolved_gaps") or []
    if gaps:
        story.append(_p("6a. Unresolved Gaps — Best Guess, Not a Finding", "CWH2"))
        story.append(_p(
            "Each best-guess answer below is the AI's inference from the available evidence only. "
            "It is <b>not</b> a conclusion and has <b>not</b> been independently verified.", "CWWarn"))
        story.append(Spacer(1, 4))
        for g in gaps:
            story.append(_p(f"<b>{esc(g['question'])}</b>", "CWBody"))
            if g.get("best_guess"):
                basis = f" — basis: {esc(g['basis'])}" if g.get("basis") else ""
                story.append(_p(
                    f"Possible answer (unverified, {esc(g.get('confidence', 'none'))} confidence): "
                    f"{esc(g['best_guess'])}{basis}", "CWSmall"))
            else:
                story.append(_p("No basis in the evidence for even a tentative guess.", "CWSmall"))
            story.append(Spacer(1, 4))

    # --- 7. Legal authorities ---
    story.append(_p("7. Relevant Legal Authorities", "CWH2"))
    if legal_results:
        for r in legal_results:
            story.append(_p(f"<b>{esc(r['title'])}</b> (similarity: {esc(r['similarity_score'])})", "CWBody"))
            story.append(_p(esc(r["passage"][:300]) + "...", "CWSmall"))
            if r.get("source_url"):
                story.append(_p(esc(r["source_url"]), "CWSmall"))
            story.append(Spacer(1, 4))
    else:
        story.append(_p("No legal query was run for this report.", "CWBody"))

    # --- 8. Audit trail ---
    story.append(_p("8. Tamper-Evident Audit Trail & Chain of Custody", "CWH2"))
    chain_color = "CWBody" if chain_ok else "CWWarn"
    story.append(_p(f"<b>Total audit events logged:</b> {audit_count}", "CWBody"))
    story.append(_p(f"<b>Cryptographic Hash-Chain Integrity:</b> {'PASSED (Unbroken Chain)' if chain_ok else 'FAILED (Tampering Detected)'}", chain_color))
    story.append(Spacer(1, 4))

    # Fetch recent audit events to include real audit ledger summary table in PDF
    audit_conn = get_conn()
    cur = audit_conn.cursor()
    cur.execute("SELECT timestamp, actor_role, action, target, this_hash FROM audit_events WHERE case_id=? ORDER BY timestamp ASC", (case_id,))
    recent_events = cur.fetchall()
    audit_conn.close()
    if recent_events:
        audit_rows = [[
            _p("Timestamp (UTC)", "CWCellHeader"),
            _p("Actor", "CWCellHeader"),
            _p("Action", "CWCellHeader"),
            _p("Target", "CWCellHeader"),
            _p("Block Hash", "CWCellHeader"),
        ]]
        for a in recent_events:
            audit_rows.append([
                _p(f"<font size=7>{esc(a['timestamp'][:19].replace('T', ' '))}</font>", "CWCell"),
                _p(f"<font size=7>{esc(a.get('actor_role') or a.get('actor') or 'system')}</font>", "CWCell"),
                _p(f"<font size=7>{esc(a['action'][:32])}</font>", "CWCell"),
                _p(f"<font size=7>{esc(a.get('target', '')[:24])}</font>", "CWCell"),
                _p(f"<font size=6.5 fontName='Courier'>{esc(a['this_hash'][:14])}...</font>", "CWCell"),
            ])
        aud_table = Table(audit_rows, colWidths=[32 * mm, 18 * mm, 50 * mm, 42 * mm, 38 * mm], repeatRows=1)
        aud_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d4d4d8")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(aud_table)
    story.append(Spacer(1, 8))

    # --- 9. Disclosure ---
    story.append(_p("9. Notice on AI-assisted analysis & Statutory Disclaimers", "CWH2"))
    story.append(_p(
        "<b>Notice of Automated AI Extraction:</b> This case file was parsed and analyzed using CaseWeave's "
        "multi-model pipeline (Meta first; a local model, Groq or Gemini only if Meta could not answer; the audit log records which). Observations, timelines, and reconstructed "
        "narratives represent investigative hypotheses derived strictly from uploaded evidentiary records. "
        "<b>They do not constitute statutory conclusions of guilt, judicial findings, or formal police charges.</b> "
        "Every identified discrepancy and factual claim must be independently verified against original exhibits "
        "prior to submission before a magistrate or court of law.", "CWBody"))
    story.append(Spacer(1, 4))
    story.append(_p(
        "<b>Integrity:</b> evidence originals are hashed with SHA-256 on upload and re-verified before they are processed or served; "
        "every action is recorded in a keyed, hash-chained audit log. Use in proceedings still requires review by counsel and a "
        "Section 63 Bharatiya Sakshya Adhiniyam, 2023 certificate for each electronic record.", "CWSmall"))

    doc.build(story)
    return out_path
