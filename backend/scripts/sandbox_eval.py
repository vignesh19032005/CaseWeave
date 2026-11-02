"""Measures how trustworthy the checking layer is, with numbers, on random scenes.

  python scripts/sandbox_eval.py [scenes] [first_seed]

1. Determinism: the same input gives the same scene and the same plan, every time.
2. Fault detection: valid plans are deliberately damaged (a walk through a wall, an
   impossible sprint, a jump in position) and the independent validator must object.
3. False alarms: undamaged plans that the planner produced must not be rejected for a
   physical reason the validator cannot explain (reported as 'unexplained').

It uses only the geometry engine, so it needs no database, model or network.
"""
import copy
import json
import os
import random
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tests"))
os.chdir(BACKEND)

from pipeline import sandbox_geometry as sg  # noqa: E402
from test_sandbox_geometry import random_raw, random_steps, blocked, DISCLOSED  # noqa: E402


def digest(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


def main(n: int, base: int) -> None:
    det_ok = det_total = 0
    inj = {"wall": [0, 0], "sprint": [0, 0], "jump": [0, 0]}  # [detected, injected]
    unexplained = clean_scenes = 0
    for seed in range(base, base + n):
        rng = random.Random(seed)
        raw = random_raw(rng)
        lay = sg.build_layout(raw, set())
        steps, actors = random_steps(rng, lay)
        plan = sg.plan_scenario(steps, lay, actors)
        det_total += 1
        lay2 = sg.build_layout(raw, set())
        plan2 = sg.plan_scenario(steps, lay2, actors)
        det_ok += digest(lay) == digest(lay2) and digest(plan) == digest(plan2)
        val = sg.validate_plan(plan, lay)
        if val["is_physically_possible"]:
            clean_scenes += 1
        elif blocked(val) and not [v for v in val["violations"] if v["code"] in DISCLOSED]:
            unexplained += 1
        if not val["is_physically_possible"]:
            continue
        # (a) push one walking leg's far point 6 m sideways, into whatever is there, outside the walkable area
        walks = [(ai, si) for ai, a in enumerate(plan["actors"]) for si, s in enumerate(a["segments"]) if s["kind"] == "transit" and s.get("route") and len(s["route"]) >= 2]
        if not walks:
            continue
        ai, si = random.Random(seed).choice(walks)
        bad = copy.deepcopy(plan)
        seg = bad["actors"][ai]["segments"][si]
        seg["route"][-1] = [seg["route"][-1][0] + 400.0, seg["route"][-1][1], seg["route"][-1][2]]
        inj["wall"][1] += 1
        inj["wall"][0] += not sg.validate_plan(bad, lay)["is_physically_possible"]
        # (b) squeeze a walk into a tenth of its time: a sprint nobody can sustain
        bad = copy.deepcopy(plan)
        seg = bad["actors"][ai]["segments"][si]
        if seg["t1"] - seg["t0"] > 1.0 and (seg.get("length_m") or 0) > 8.0:
            seg["t1"] = seg["t0"] + (seg["t1"] - seg["t0"]) / 10.0
            seg["v_max"] = (seg.get("v_max") or 1.4) * 10.0
            inj["sprint"][1] += 1
            inj["sprint"][0] += not sg.validate_plan(bad, lay)["is_physically_possible"]
        # (c) a stop that is not where the walk before it ended
        bad = copy.deepcopy(plan)
        dw = [(a2, s2) for a2, a in enumerate(bad["actors"]) for s2, s in enumerate(a["segments"]) if s["kind"] == "dwell" and s2 > 0]
        if dw:
            a2, s2 = dw[0]
            p = bad["actors"][a2]["segments"][s2]["pos"]
            bad["actors"][a2]["segments"][s2]["pos"] = [p[0] + 3.0, p[1], p[2] + 3.0]
            inj["jump"][1] += 1
            inj["jump"][0] += not sg.validate_plan(bad, lay)["is_physically_possible"]
    print(f"scenes checked: {n} (seeds {base}..{base + n - 1}); {clean_scenes} had a fully consistent plan")
    print(f"determinism: {det_ok}/{det_total} identical on rebuild")
    for k, (d, t) in inj.items():
        print(f"fault detection - {k}: {d}/{t}" + (f" ({100 * d / t:.1f}%)" if t else ""))
    print(f"unexplained rejections of planner output: {unexplained}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 300, int(sys.argv[2]) if len(sys.argv) > 2 else 1)
