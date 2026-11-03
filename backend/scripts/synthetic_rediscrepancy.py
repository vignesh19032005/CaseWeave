"""Re-runs only the contradiction detection (timeline + debate) for an existing synthetic case and updates its saved results.

  python scripts/synthetic_rediscrepancy.py <folder> <case id> [meta_only|local_only]

Used after the detector itself changed, so every case is measured with the same detector without regenerating scenes.
"""
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))
folder, case_id = sys.argv[1], sys.argv[2]
mode = sys.argv[3] if len(sys.argv) > 3 else "meta_only"
os.environ["LLM_PROVIDER_MODE"] = mode

import logging  # noqa: E402
logging.disable(logging.WARNING)
from pipeline.timeline import build_timeline  # noqa: E402
from pipeline.discrepancy import detect_discrepancies  # noqa: E402
from db import get_conn  # noqa: E402

events = build_timeline(case_id)
conflicts, links = detect_discrepancies(case_id, events)
print(folder, case_id, "timeline", len(events), "conflicts", len(conflicts), "links", len(links), flush=True)
with get_conn() as conn:
    rows = [dict(r) for r in conn.execute("SELECT * FROM conflicts WHERE case_id=?", (case_id,)).fetchall()]
p = BACKEND / "data" / "synthetic_cases" / "results" / f"{folder}__{mode}.json"
d = json.loads(p.read_text(encoding="utf-8"))
d["conflicts"] = rows
p.write_text(json.dumps(d, default=str), encoding="utf-8")
for r in rows:
    print(" -", (r["claim_a"] or "")[:70], "|", (r["claim_b"] or "")[:70])
