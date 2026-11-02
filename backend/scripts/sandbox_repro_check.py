"""Measures how much the scene layout changes between runs for the same evidence.

Calls the real language model N times (costs quota; run deliberately), builds each
layout exactly as production does, saves NOTHING, and prints a similarity matrix.
A low score means the model's reading of the evidence is unstable for this case:
approve one layout and use "new scenarios on this layout" so results stay
reproducible, instead of rebuilding the room each time.

    python scripts/sandbox_repro_check.py CW-E65FA6 3
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import sandbox, sandbox_evidence as evd, sandbox_geometry as geo  # noqa: E402
from pipeline.redaction import build_redactor, redaction_enabled  # noqa: E402


def main(case_id: str, runs: int) -> None:
    ev = evd.gather_evidence(case_id)
    known = evd.known_refs(ev)
    context, _ = evd.evidence_context(ev)
    redactor = build_redactor(ev["entities"], redaction_enabled())
    layouts = []
    for i in range(runs):
        call = sandbox._call_model(sandbox.LAYOUT_SYSTEM_PROMPT, f"Case ID: {case_id}\n\n{context}\n\nDescribe the physical scene.", 4096, f"repro_{i + 1}", redactor)
        layouts.append(geo.build_layout(call["parsed"] if isinstance(call["parsed"], dict) else {}, known))
        lay = layouts[-1]
        print(f"run {i + 1}: {len(lay['rooms'])} rooms, {len(lay['fixtures'])} furniture, {len(lay['openings'])} doors, via {call['provider']}/{call['model']}")
    worst = 1.0
    for i in range(runs):
        for j in range(i + 1, runs):
            sim = geo.layout_similarity(layouts[i], layouts[j])
            worst = min(worst, sim["score"])
            print(f"run {i + 1} vs {j + 1}: similarity {sim['score']:.2f} {sim['parts']} {'OK' if sim['within_tolerance'] else 'UNSTABLE'}")
    print("verdict:", "stable enough to reuse" if worst >= 0.8 else "unstable: approve one layout and reuse it")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "", int(sys.argv[2]) if len(sys.argv) > 2 else 3)
