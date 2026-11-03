"""
Printable review pack for the scene reconstruction: the same content as the JSON
pack, laid out for a reviewer or a court file. It carries the disclaimer on every
page, floor plans with each person's route, every scenario's checks and
citations, the model calls that produced it, and the audit trail.
"""
from __future__ import annotations

import io
import os
from typing import Any, Dict, List

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from pipeline.pdf_fonts import FONT as _FONT, UNICODE as _UNICODE  # noqa: E402


def _t(v: Any) -> str:
    s = "" if v is None else str(v)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return s if _UNICODE else s.encode("latin-1", "replace").decode("latin-1")


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName=_FONT, fontSize=17, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=_FONT, fontSize=12.5, spaceBefore=10, spaceAfter=4),
        "p": ParagraphStyle("p", parent=base["BodyText"], fontName=_FONT, fontSize=8.8, leading=11.5),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontName=_FONT, fontSize=7.4, leading=9.4, textColor=colors.HexColor("#444444")),
        "warn": ParagraphStyle("warn", parent=base["BodyText"], fontName=_FONT, fontSize=8.4, leading=11, textColor=colors.HexColor("#8a4b00"),
                               backColor=colors.HexColor("#fff4e0"), borderPadding=4),
        "bad": ParagraphStyle("bad", parent=base["BodyText"], fontName=_FONT, fontSize=8.4, leading=11, textColor=colors.HexColor("#a30000")),
        "cell": ParagraphStyle("cell", parent=base["BodyText"], fontName=_FONT, fontSize=7.3, leading=9),
    }


_STATE_COLOR = {"forced": colors.HexColor("#d92d20"), "intact": colors.HexColor("#16a34a"), "locked": colors.HexColor("#7c3aed"),
                "open": colors.HexColor("#0ea5e9"), "unknown": colors.HexColor("#94a3b8")}


def _floor_plan(layout: Dict[str, Any], level: int, scenario: Dict[str, Any] | None, width: float = 480, height: float = 330) -> Drawing:
    rooms = [r for r in layout["rooms"] if r["level"] == level]
    d = Drawing(width, height)
    if not rooms:
        return d
    xs = [v for r in layout["rooms"] if r["level"] == 0 for v in (r["rect"][0], r["rect"][1])] if level != 0 else []
    x0 = min([r["rect"][0] for r in rooms] + ([min(xs)] if xs else []))
    x1 = max([r["rect"][1] for r in rooms] + ([max(xs)] if xs else []))
    z0, z1 = min(r["rect"][2] for r in rooms), max(r["rect"][3] for r in rooms)
    pad = 6.0 if level == 0 else 1.0
    x0, x1, z0, z1 = x0 - pad, x1 + pad, z0 - pad, z1 + pad
    sc = min((width - 20) / max(x1 - x0, 1e-6), (height - 24) / max(z1 - z0, 1e-6))
    ox, oz = 10 - x0 * sc, 12 - z0 * sc

    def P(x: float, z: float):
        return ox + x * sc, oz + z * sc

    for r in rooms:
        ax, az = P(r["rect"][0], r["rect"][2])
        bx, bz = P(r["rect"][1], r["rect"][3])
        d.add(Rect(ax, az, bx - ax, bz - az, strokeColor=colors.HexColor("#475569"), fillColor=colors.HexColor("#f1f5f9" if r.get("observed", True) else "#e2e8f0"), strokeWidth=1.2))
        d.add(String(ax + 3, bz - 9, _t(r["label"])[:34], fontName=_FONT, fontSize=6.5, fillColor=colors.HexColor("#334155")))
    for f in layout["fixtures"]:
        if f["room"] in {r["id"] for r in rooms}:
            ax, az = P(f["pos"][0] - f["footprint_m"][0] / 2, f["pos"][2] - f["footprint_m"][1] / 2)
            bx, bz = P(f["pos"][0] + f["footprint_m"][0] / 2, f["pos"][2] + f["footprint_m"][1] / 2)
            d.add(Rect(ax, az, bx - ax, bz - az, strokeColor=colors.HexColor("#f43f5e" if f["basis"] == "assumed" else "#475569"), fillColor=colors.HexColor("#d6c7a8"), strokeWidth=0.6))
    if level == 0:
        for o in layout.get("outdoor_objects", []):
            ax, az = P(o["pos"][0] - o["footprint_m"][0] / 2, o["pos"][2] - o["footprint_m"][1] / 2)
            bx, bz = P(o["pos"][0] + o["footprint_m"][0] / 2, o["pos"][2] + o["footprint_m"][1] / 2)
            d.add(Rect(ax, az, bx - ax, bz - az, strokeColor=colors.HexColor("#64748b"), fillColor=colors.HexColor("#cbd5e1"), strokeWidth=0.6))
    for op in layout["openings"]:
        if op["kind"] == "stairs":
            if op["room_a"] in {r["id"] for r in rooms} or op["room_b"] in {r["id"] for r in rooms}:
                px, pz = P(op["gap_pos"][0], op["gap_pos"][2])
                d.add(Rect(px - 4, pz - 4, 8, 8, strokeColor=colors.black, fillColor=colors.HexColor("#fde68a"), strokeWidth=0.6))
            continue
        if op["level"] != level:
            continue
        w = op["width_m"] / 2
        if op["orient"] == "z":
            a, b = P(op["line"], op["gap_center_m"] - w), P(op["line"], op["gap_center_m"] + w)
        else:
            a, b = P(op["gap_center_m"] - w, op["line"]), P(op["gap_center_m"] + w, op["line"])
        d.add(Line(a[0], a[1], b[0], b[1], strokeColor=_STATE_COLOR.get(op["state"], colors.grey), strokeWidth=3.2))
    for ob in layout.get("observers", []):
        if ob["level"] == level:
            px, pz = P(ob["pos"][0], ob["pos"][2])
            d.add(Circle(px, pz, 2.8, fillColor=colors.HexColor("#2563eb" if ob["kind"] == "camera" else "#9333ea"), strokeColor=colors.black, strokeWidth=0.4))
    if scenario:
        for a in scenario["plan"]["actors"]:
            col = colors.HexColor(a["color"])
            for sgm in a["segments"]:
                if sgm["kind"] != "transit":
                    continue
                pts = []
                for x, y, z in sgm["route"]:
                    lvl_y = {f["level"]: f["floor_y"] for f in layout["levels"]}.get(level, 0.0)
                    if abs(y - lvl_y) < 0.3:
                        pts += list(P(x, z))
                if len(pts) >= 4:
                    d.add(PolyLine(pts, strokeColor=col, strokeWidth=1.3))
    return d


def render_pack_pdf(pack: Dict[str, Any]) -> bytes:
    st = _styles()
    buf = io.BytesIO()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(_FONT, 6.8)
        canvas.setFillColor(colors.HexColor("#8a4b00"))
        canvas.drawString(14 * mm, 8 * mm, "Investigative hypothesis visualisation - not a record of what happened. Review by a qualified forensic examiner and legal counsel is required for any use in proceedings.")
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Page {doc.page}  |  case {_t(pack.get('case_id'))}  |  pack {str(pack.get('pack_hash', ''))[:12]}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                            title=f"CaseWeave scene review {pack.get('case_id')}", author="CaseWeave")
    run = pack["run"]
    layout = run["layout"]
    story: List[Any] = []
    story += [Paragraph("Scene reconstruction - review pack", st["h1"]), Paragraph(_t(pack["disclaimer"]), st["warn"]), Spacer(1, 6)]
    meta_rows = [["Case", _t(pack["case_id"])], ["Exported", f"{_t(pack['exported_at'])} by {_t(pack.get('exported_by'))}"], ["Scene version", f"{_t(run['run_id'])}  ({_t(run['mode'])}, created {_t(run['created_at'])} by {_t(run['created_by'])})"],
                 ["Layout approved", _t(f"{run['approved_by']} at {run['approved_at']}") if run.get("approved_by") else "Not yet approved by a reviewer"],
                 ["Engine", f"{_t(pack.get('engine_version'))} (schema {pack.get('schema_version')})"], ["Pack hash", _t(pack.get("pack_hash"))],
                 ["Audit chain", "verified intact" if pack.get("audit_chain_verified") else "NOT VERIFIED"],
                 ["Evidence changed since", "YES - " + _t(pack.get("evidence_change_detail")) if pack.get("evidence_changed_since_generation") else "No"]]
    story.append(Table([[Paragraph(k, st["cell"]), Paragraph(v, st["cell"])] for k, v in meta_rows], colWidths=[40 * mm, 142 * mm],
                       style=TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9"))])))
    red = pack.get("redaction") or {}
    story += [Paragraph("Privacy", st["h2"]), Paragraph(_t(
        ("Names and identifiers were replaced with placeholders before text was sent to the language model. " if red.get("enabled") else "Redaction was OFF for this run. ")
        + f"Replacements: {red.get('replacements') or 'none'}. Not covered: " + "; ".join(red.get("not_covered", [])) + "."), st["p"])]

    story += [Paragraph("The scene", st["h2"])]
    cov = layout.get("coverage", {})
    story.append(Paragraph(_t(f"{len(layout['rooms'])} room(s) on {len({r['level'] for r in layout['rooms']})} floor(s); {len(layout['openings'])} door/stairs; {len(layout['fixtures'])} furniture; "
                              f"{len(layout.get('observers', []))} camera/witness. Basis: {cov.get('stated', 0)} stated, {cov.get('inferred', 0)} inferred, {cov.get('assumed', 0)} assumed, {cov.get('officer', 0)} officer-supplied."), st["p"]))
    rows = [["Room", "Floor", "Size (m)", "Size basis", "Described by evidence"]] + [
        [Paragraph(_t(r["label"]), st["cell"]), r["level"], f"{r['width_m']:.1f} x {r['length_m']:.1f}", _t(r.get("dimensions_basis")), "yes" if r.get("observed", True) else "NO"] for r in layout["rooms"]]
    story.append(Table(rows, colWidths=[62 * mm, 14 * mm, 28 * mm, 30 * mm, 48 * mm], repeatRows=1,
                       style=TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")), ("FONTNAME", (0, 0), (-1, -1), _FONT), ("FONTSIZE", (0, 0), (-1, -1), 7.3)])))
    for title, items, style in (("Assumptions and defaults", layout.get("defaults_used", []), "warn"), ("Adjustments and warnings", layout.get("warnings", []), "p"), ("Limits", layout.get("limits", []), "p")):
        if items:
            story += [Paragraph(title, st["h2"])] + [Paragraph("- " + _t(x), st[style]) for x in items]
    if layout.get("notes"):
        story.append(Paragraph("Model note: " + _t(layout["notes"]), st["small"]))

    top = next((s for s in pack["scenarios"] if s.get("status") == "active" and s.get("scenario_type") == "automated"), None)
    for lvl in sorted({r["level"] for r in layout["rooms"]}):
        story += [Paragraph(f"Floor plan - floor {lvl}" + (f" with routes of '{_t(top['title'])}'" if top else ""), st["h2"]), _floor_plan(layout, lvl, top),
                  Paragraph("Door colour: red forced, green intact, purple locked, blue open, grey unknown. Pink outline: assumed object. Blue dot: camera, purple dot: witness. Coloured lines: each person's walking route.", st["small"])]

    for s in pack["scenarios"]:
        story.append(PageBreak())
        who = "Officer theory" if s["scenario_type"] == "officer_custom" else f"Candidate #{s.get('rank')}"
        story += [Paragraph(f"{who}: {_t(s['title'])}" + ("  [WITHDRAWN]" if s.get("status") == "retracted" else ""), st["h1"]), Paragraph(_t(s["hypothesis_summary"]), st["p"])]
        if s.get("retracted"):
            story.append(Paragraph("Withdrawn by " + _t(s["retracted"]["by"]) + " on " + _t(s["retracted"]["at"]) + ": " + _t(s["retracted"]["reason"]), st["bad"]))
        sc = s["score"]
        story.append(Paragraph(_t(f"Evidence support score {sc['verifiable_score']}/100 (a ranking aid, not a probability). The model's own estimate was {sc['llm_estimate']}% and was not used for ranking. "
                                  f"{sc['components']['steps_citing_evidence']} of {sc['components']['steps_total']} steps cite relevant evidence. {sc.get('cap_reason') or ''}"), st["p"]))
        story.append(Paragraph(_t("Formula: " + sc["formula"]), st["small"]))
        v = s["validation"]
        story.append(Paragraph("Physical and timing checks: " + ("consistent" if v["is_physically_possible"] else f"{len(v['violations'])} problem(s)"), st["h2"]))
        story += [Paragraph("PROBLEM: " + _t(x["message"]), st["bad"]) for x in v["violations"]] + [Paragraph("Caution: " + _t(w), st["p"]) for w in v["warnings"]]
        story.append(Paragraph(_t("Checked: " + "; ".join(v["checks_run"]) + ".  NOT checked: " + "; ".join(v["checks_not_run"]) + "."), st["small"]))
        if v.get("observation_checks"):
            story.append(Paragraph(_t("Camera/witness claims: " + "; ".join(f"step {c['step'] + 1} by {c['observer']}: {'seen' if c['visible'] else 'NOT possible - ' + c['reason']}" for c in v["observation_checks"])), st["small"]))
        story += [Paragraph("People and steps", st["h2"])]
        rows = [["Person", "#", "Place", "Action", "Starts at", "Evidence cited"]]
        for a in s["plan"]["actors"]:
            for stp in a["steps"]:
                rows.append([Paragraph(_t(a["label"]), st["cell"]), stp["k"] + 1, Paragraph(_t(stp["label"]), st["cell"]), _t(stp["action"].replace("_", " ")), f"{stp['arrive_s']:.0f} s",
                             Paragraph(_t(", ".join(stp["evidence_refs"]) or "none (inferred)"), st["cell"])])
        story.append(Table(rows, colWidths=[26 * mm, 8 * mm, 52 * mm, 24 * mm, 18 * mm, 54 * mm], repeatRows=1,
                           style=TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                                             ("FONTNAME", (0, 0), (-1, -1), _FONT), ("FONTSIZE", (0, 0), (-1, -1), 7.3), ("VALIGN", (0, 0), (-1, -1), "TOP")])))
        if s["plan"]["route_notes"]:
            story += [Paragraph("Where the system chose or adjusted the route", st["h2"])] + [Paragraph("- " + _t(n), st["small"]) for n in s["plan"]["route_notes"]]
        t = s["time"]
        story += [Paragraph("Clock times", st["h2"]), Paragraph(_t(t["note"]), st["p"])] + [
            Paragraph(_t(f"{a['actor_label']} step {a['step'] + 1} ({a['label']}) at {a['clock_text']} from {a['observation_id']}"), st["small"]) for a in t["anchors"]]
        for key, title in (("supporting_facts", "Supporting points"), ("contradicted_points", "Points against, or unresolved")):
            if s.get(key):
                story.append(Paragraph(title, st["h2"]))
                for f in s[key]:
                    story.append(Paragraph("- " + _t(f["text"]) + "  [" + _t(", ".join(f["refs"]) or "no citation") + "]", st["small"]))
        if s.get("evidence_index"):
            story.append(Paragraph("Evidence cited (as it stood when this was generated)", st["h2"]))
            for e in s["evidence_index"].values():
                story.append(Paragraph(_t(f"{e['id']} ({e['kind']}{', ' + e['time'] if e.get('time') else ''}{', ' + e['filename'] if e.get('filename') else ''}): {e['text']}"), st["small"]))

    story += [PageBreak(), Paragraph("How this was produced", st["h1"])]
    calls = pack.get("raw_model_calls", [])
    rows = [["Step", "Provider / model", "Prompt hash", "Seconds"]] + [[_t(c["step"]), _t(f"{c['provider']} / {c['model']}"), _t(str(c["prompt_hash"])[:16]), c.get("seconds")] for c in calls]
    story.append(Table(rows, colWidths=[45 * mm, 62 * mm, 50 * mm, 24 * mm], style=TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")), ("FONTNAME", (0, 0), (-1, -1), _FONT), ("FONTSIZE", (0, 0), (-1, -1), 7.3)])))
    story.append(Paragraph("The full model replies are in the JSON review pack.", st["small"]))
    story += [Paragraph("Audit trail (scene reconstruction events)", st["h2"])]
    rows = [["When (UTC)", "Role", "Action", "Target"]] + [[_t(e["timestamp"])[:19], _t(e["actor_role"]), _t(e["action"]), Paragraph(_t(e["target"]), st["cell"])] for e in pack.get("audit_events", [])]
    story.append(Table(rows, colWidths=[34 * mm, 22 * mm, 56 * mm, 69 * mm], repeatRows=1, style=TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")), ("FONTNAME", (0, 0), (-1, -1), _FONT), ("FONTSIZE", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "TOP")])))
    cfg = pack.get("engine_config") or {}
    story += [Paragraph("Engine settings used", st["h2"]), Paragraph(_t(", ".join(f"{k}={v}" for k, v in cfg.items())), st["small"])]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
