"""
Draft electronic-evidence certificate, modeled on the kind of statement
Bharatiya Sakshya Adhiniyam (BSA) 2023 s.63 requires to accompany an
electronic record for it to be admissible: identifying the device/process
that produced the record, confirming it was produced by a device in
regular use, and giving an integrity proof (the hash).

This is a DRAFT for a lawyer to review and formally execute — it is not
itself a legal certificate and makes no claim to be one. Built entirely
from data already in the system (upload hash, audit trail, extraction
method) — no new verification work, just a formatted summary of what
CaseWeave already recorded.
"""
import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

from db import get_conn
from pipeline.pdf_fonts import FONT, FONT_BOLD, fit

NAVY = colors.HexColor("#1e3a5f")
AMBER = colors.HexColor("#92620a")
GREY = colors.HexColor("#52525b")

_styles = getSampleStyleSheet()
for _name in ("Title", "Normal", "Heading2"):
    _styles[_name].fontName = FONT_BOLD if _name != "Normal" else FONT
_styles.add(ParagraphStyle("CertTitle", parent=_styles["Title"], textColor=NAVY, fontSize=16, spaceAfter=4))
_styles.add(ParagraphStyle("CertBanner", parent=_styles["Normal"], textColor=colors.white, fontSize=10,
                           leading=13, alignment=1))
_styles.add(ParagraphStyle("CertH2", parent=_styles["Heading2"], textColor=NAVY, fontSize=11, spaceBefore=14, spaceAfter=6))
_styles.add(ParagraphStyle("CertBody", parent=_styles["Normal"], fontSize=9.5, leading=14))
_styles.add(ParagraphStyle("CertSmall", parent=_styles["Normal"], fontSize=8, leading=11, textColor=GREY))


def _esc(text) -> str:
    return fit(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _p(markup: str, style: str = "CertBody") -> Paragraph:
    return Paragraph(markup, _styles[style])


def generate_evidence_certificate(case_id: str, evidence_id: str, out_path: Path, integrity: str = "not checked") -> Path:
    """integrity: "verified" (the stored file was re-hashed just now and matches), "FAILED", "missing" or "not checked"."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cases WHERE case_id=?", (case_id,))
    case = cur.fetchone()
    cur.execute("SELECT * FROM evidence_items WHERE case_id=? AND evidence_id=?", (case_id, evidence_id))
    item = cur.fetchone()
    if not item:
        conn.close()
        raise ValueError(f"evidence item not found: {evidence_id}")

    cur.execute(
        "SELECT * FROM audit_events WHERE case_id=? AND target=? ORDER BY timestamp ASC",
        (case_id, evidence_id),
    )
    events = cur.fetchall()
    conn.close()

    upload_event = next((e for e in events if e["action"] == "evidence_uploaded"), None)
    extraction_event = next((e for e in reversed(events) if e["action"].startswith("extracted_")), None)

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
        title=f"Draft Electronic Evidence Certificate — {evidence_id}",
    )
    story = []

    banner = Table([[_p("DRAFT — NOT A LEGAL CERTIFICATE — FOR REVIEW AND FORMAL EXECUTION BY COUNSEL ONLY", "CertBanner")]],
                    colWidths=[166 * mm])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AMBER),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(banner)
    story.append(Spacer(1, 12))

    story.append(_p("Draft Certificate — Electronic Record", "CertTitle"))
    story.append(_p(
        "Prepared to assist a certificate under Section 63, Bharatiya Sakshya Adhiniyam, 2023 "
        "(certificate for electronic evidence). This draft summarizes what CaseWeave recorded about "
        "this record's production and integrity; it does not itself satisfy s.63 and must be reviewed, "
        "corrected if needed, and formally executed by the person responsible for the device/process "
        "before use.", "CertSmall"))
    story.append(HRFlowable(width="100%", thickness=1, color=NAVY, spaceBefore=10, spaceAfter=10))

    story.append(_p("1. Record Identification", "CertH2"))
    rows = [
        ["Case", f"{_esc(case['title'])} ({_esc(case_id)})"],
        ["Evidence ID", _esc(evidence_id)],
        ["File name", _esc(item["filename"])],
        ["Declared type", _esc(item["evidence_type"])],
        ["SHA-256 hash", _esc(item["file_hash"])],
    ]
    t = Table(rows, colWidths=[40 * mm, 126 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), GREY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e4e4e7")),
    ]))
    story.append(t)

    story.append(_p("2. Production and Custody", "CertH2"))
    if upload_event:
        story.append(_p(
            f"This record was ingested into CaseWeave on {_esc(upload_event['timestamp'])} UTC "
            f"by user role &ldquo;{_esc(upload_event['actor_role'])}&rdquo;. A SHA-256 hash was computed "
            f"on upload and verified against a second read of the stored copy at write time (see hash above). "
            + {
                "verified": "The stored original was re-hashed when this draft was generated and still matches that hash. ",
                "FAILED": "<b>WARNING: the stored original, re-hashed when this draft was generated, does NOT match the hash recorded at upload. Do not rely on this record.</b> ",
                "missing": "<b>WARNING: the stored original could not be found when this draft was generated.</b> ",
            }.get(integrity, "The stored original was not re-hashed when this draft was generated. ")
            + f"The hash-chained audit log (available separately) records every action taken on this case.", "CertBody"))
    else:
        story.append(_p("No upload event was found in the audit log for this item.", "CertBody"))

    story.append(_p("3. Extraction / Processing Method", "CertH2"))
    if extraction_event:
        story.append(_p(
            f"Content was extracted from this record using method "
            f"&ldquo;{_esc(extraction_event['action'].replace('extracted_', ''))}&rdquo; on "
            f"{_esc(extraction_event['timestamp'])} UTC. This is an automated software process (CaseWeave's "
            f"Stage 1 media extraction pipeline), not manual transcription.", "CertBody"))
    else:
        story.append(_p(
            "No extraction event was recorded for this item — either it has not yet been processed, "
            "or it is a plain text/structured log file read directly without a separate extraction step.",
            "CertBody"))

    story.append(_p("4. Statement for Counsel to Complete", "CertH2"))
    story.append(_p(
        "I, ______________________________ (name, designation), state that the above electronic record "
        "was produced by a computer/device used regularly for [describe activity] during the period over "
        "which the record was produced, that the device was operating properly during that period, and "
        "that the information was supplied in the ordinary course of that activity. I certify the above "
        "particulars to the best of my knowledge and belief.", "CertBody"))
    story.append(Spacer(1, 24))
    story.append(_p("Signature: _______________________    Date: _______________", "CertBody"))
    story.append(_p("Name &amp; designation: _______________________________________", "CertBody"))

    story.append(Spacer(1, 16))
    story.append(_p(
        f"Generated by CaseWeave {datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).strftime('%d %b %Y, %H:%M UTC')} — "
        f"this generation event itself is not independent proof of anything stated above; it is a "
        f"formatting aid drawn from this system's own records.", "CertSmall"))

    doc.build(story)
    return out_path
