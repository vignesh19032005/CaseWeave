"""Stage 3 completion: a real viewable HTML timeline artifact, not just DB rows.
This is the first genuinely demo-able screen per PLAN.md's milestone table —
click an event, see its source. No framework, single self-contained file."""
import html
from pathlib import Path


def render_timeline_html(case_id: str, title: str, timeline_events: list, conflicts: list, out_path: Path):
    conflict_event_pairs = set()
    for c in conflicts:
        conflict_event_pairs.add((c["source_a"], c["time_a"]))
        conflict_event_pairs.add((c["source_b"], c["time_b"]))

    rows = []
    for e in timeline_events:
        is_conflict = (e["source_evidence_id"], e["time"]) in conflict_event_pairs
        badge_class = "badge-conflict" if is_conflict else f"badge-{e['classification']}"
        rows.append(f"""
        <div class="event{' event-conflict' if is_conflict else ''}" data-source="{html.escape(e['source_evidence_id'])}">
          <div class="event-time">{html.escape(e['time'] or '')}</div>
          <div class="event-body">
            <span class="badge {badge_class}">{html.escape(e['classification'])}</span>
            <span class="event-desc">{html.escape(e['description'])}</span>
            <div class="event-source">source: <code>{html.escape(e['source_evidence_id'])}</code></div>
          </div>
        </div>""")

    conflict_rows = []
    for c in conflicts:
        conflict_rows.append(f"""
        <div class="conflict">
          <div class="conflict-title">Conflict</div>
          <div><strong>A</strong> ({html.escape(c['time_a'] or '')}, <code>{html.escape(c['source_a'])}</code>): {html.escape(c['claim_a'])}</div>
          <div><strong>B</strong> ({html.escape(c['time_b'] or '')}, <code>{html.escape(c['source_b'])}</code>): {html.escape(c['claim_b'])}</div>
          <div class="conflict-nature">{html.escape(c.get('nature_of_conflict', ''))}</div>
          <div class="conflict-question">{html.escape(c.get('question', ''))}</div>
        </div>""")

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CaseWeave — {html.escape(title)}</title>
<style>
  :root {{
    --bg: #0b0d12; --panel: #141821; --border: #262b36; --text: #e6e9ef; --muted: #8a93a6;
    --observed: #2f6f4f; --reported: #5a4a9e; --inferred: #9e7a2f; --unknown: #6b6f78; --conflict: #a23b3b;
  }}
  * {{ box-sizing: border-box; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 24px 16px; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color: var(--muted); font-size: 13px; margin-bottom: 24px; }}
  .layout {{ display: grid; grid-template-columns: 1fr; gap: 24px; max-width: 900px; margin: 0 auto; }}
  @media (min-width: 900px) {{ .layout {{ grid-template-columns: 1fr 360px; }} }}
  .panel {{ background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }}
  .panel h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); margin: 0 0 16px; }}
  .event {{ display: flex; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border); cursor: default; }}
  .event:last-child {{ border-bottom: none; }}
  .event-time {{ flex: 0 0 64px; font-variant-numeric: tabular-nums; color: var(--muted); font-size: 13px; padding-top: 2px; }}
  .event-body {{ flex: 1; }}
  .event-desc {{ display: block; margin-top: 4px; font-size: 14px; line-height: 1.4; }}
  .event-source {{ margin-top: 4px; font-size: 11px; color: var(--muted); }}
  .badge {{ display: inline-block; font-size: 10px; text-transform: uppercase; letter-spacing: 0.03em; padding: 2px 8px; border-radius: 999px; color: #fff; }}
  .badge-observed {{ background: var(--observed); }}
  .badge-reported {{ background: var(--reported); }}
  .badge-inferred {{ background: var(--inferred); }}
  .badge-unknown {{ background: var(--unknown); }}
  .badge-conflict {{ background: var(--conflict); }}
  .event-conflict {{ background: rgba(162,59,59,0.08); border-radius: 6px; padding-left: 8px; margin-left: -8px; }}
  .conflict {{ border: 1px solid var(--conflict); border-radius: 8px; padding: 12px; margin-bottom: 12px; font-size: 13px; }}
  .conflict-title {{ color: var(--conflict); font-weight: 600; font-size: 11px; text-transform: uppercase; margin-bottom: 8px; }}
  .conflict-nature {{ margin-top: 8px; color: var(--muted); font-style: italic; }}
  .conflict-question {{ margin-top: 8px; font-weight: 500; }}
  code {{ background: rgba(255,255,255,0.06); padding: 1px 5px; border-radius: 4px; font-size: 11px; }}
  .empty {{ color: var(--muted); font-size: 13px; }}
</style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="sub">Case {html.escape(case_id)} — evidence-linked chronology</div>
  <div class="layout">
    <div class="panel">
      <h2>Timeline</h2>
      {''.join(rows) if rows else '<div class="empty">No timed events.</div>'}
    </div>
    <div class="panel">
      <h2>Discrepancies ({len(conflicts)})</h2>
      {''.join(conflict_rows) if conflict_rows else '<div class="empty">None detected.</div>'}
    </div>
  </div>
</body>
</html>"""

    out_path.write_text(page, encoding="utf-8")
    return out_path
