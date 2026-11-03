"""Measures how often the discrepancy debate gives the same answer as a human label. Calls the REAL language model
(3 calls per pair); run it deliberately.

    python scripts/eval_discrepancy.py [repeats]

Reads tests/data/discrepancy_eval.json. For every pair it runs the Prosecutor / Defender / Judge debate `repeats` times
(default 1) and reports: overall agreement with the label, conflict precision and recall (a conflict is the verdict that
matters most), and which pairs were answered inconsistently between repeats. Add pairs from real, anonymised cases to
make the numbers meaningful: seven pairs only reveal gross problems.
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("LLM_CALL_PACING_S", "0")

from pipeline.discrepancy import _debate_adjudicate  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "tests" / "data" / "discrepancy_eval.json"


def main() -> int:
    repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    pairs = json.loads(DATA.read_text(encoding="utf-8"))["pairs"]
    rows, tp, fp, fn = [], 0, 0, 0
    for p in pairs:
        answers = []
        for _ in range(repeats):
            _, verdict, _ = _debate_adjudicate(p["a"], p["b"], "", case_id=None)
            answers.append(verdict["relationship"])
        main_answer = Counter(answers).most_common(1)[0][0]
        rows.append((p["id"], p["label"], main_answer, answers))
        if main_answer == "conflicts" and p["label"] == "conflicts":
            tp += 1
        elif main_answer == "conflicts":
            fp += 1
        elif p["label"] == "conflicts":
            fn += 1
        print(f"{p['id']:<24} label={p['label']:<10} answered={answers}", flush=True)
    agree = sum(1 for _, label, got, _ in rows if got == label or (label == "supports" and got == "related_to"))
    print(f"\nagreement with labels: {agree}/{len(rows)}")
    print(f"conflict precision: {tp}/{tp + fp}   conflict recall: {tp}/{tp + fn}")
    unstable = [r[0] for r in rows if len(set(r[3])) > 1]
    if unstable:
        print("answered differently between repeats:", ", ".join(unstable))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
