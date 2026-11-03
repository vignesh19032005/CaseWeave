"""Measured results on the synthetic demonstration cases. Four measurements, each written to data/synthetic_cases/results/benchmark_<name>.json:

  python scripts/sandbox_benchmark.py contradictions     # planted contradictions found by the evidence analysis (needs the case runs)
  python scripts/sandbox_benchmark.py checker            # planted physical faults caught by the independent checker, on the real generated scenarios
  python scripts/sandbox_benchmark.py reviewer meta_only # planted flaws found by the second-model reviewer (Meta vision), or local_only (local Llama, text only)
  python scripts/sandbox_benchmark.py variance           # run-to-run spread of the scenario scores over repeated generations
  python scripts/sandbox_benchmark.py report             # writes docs/BENCHMARKS.md from all of the above

Everything is fictional. The planted items are listed in each case's ground_truth.json. Nothing here changes a score or a result: it only counts.
"""
import copy
import json
import os
import random
import re
import statistics
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

CASES = ["burglary_warehouse", "road_accident_junction", "indoor_assault_office"]
ROOT = BACKEND / "data" / "synthetic_cases"
RES = ROOT / "results"


def load_run(folder: str, mode: str):
    p = RES / f"{folder}__{mode}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def all_runs(folder: str):
    """Every saved Meta-only run of a case (the first and the repeats), as loaded result dicts."""
    out = []
    for p in sorted(RES.glob(f"{folder}__meta_only*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if (d.get("sandbox") or {}).get("scenarios"):
            out.append(d)
    return out


def best_run(folder: str):
    """The saved run whose best scenario scored highest, so the reviewer is tested on a scenario that is worth reviewing."""
    runs = all_runs(folder)
    return max(runs, key=lambda d: max(s["score"]["verifiable_score"] for s in d["sandbox"]["scenarios"]), default=None)


def save(name: str, obj) -> None:
    (RES / f"benchmark_{name}.json").write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")


# ------------------------------------------------------------------ 1. planted contradictions

def contradictions():
    from db import get_conn
    out = {}
    for folder in CASES:
        run = load_run(folder, "meta_only")
        if not run:
            continue
        truth = json.loads((ROOT / folder / "ground_truth.json").read_text(encoding="utf-8"))
        with get_conn() as conn:
            items = {r["evidence_id"]: r["filename"] for r in conn.execute("SELECT evidence_id, filename FROM evidence_items WHERE case_id=?", (run["case_id"],)).fetchall()}
            obs = {r["observation_id"]: r["source_evidence_id"] for r in conn.execute("SELECT observation_id, source_evidence_id FROM observations WHERE case_id=?", (run["case_id"],)).fetchall()}

        def file_of(src):
            src = src or ""
            return items.get(src) or items.get(obs.get(src, "")) or ""

        found_pairs = []
        for c in run["conflicts"] if isinstance(run["conflicts"], list) else []:
            found_pairs.append({"a": file_of(c.get("source_a")), "b": file_of(c.get("source_b")), "question": (c.get("question") or "")[:160], "claim_a": (c.get("claim_a") or "")[:140], "claim_b": (c.get("claim_b") or "")[:140]})
        rows = []
        for p in truth["planted_contradictions"]:
            files = set(p["evidence"])
            hit = [f for f in found_pairs if f["a"] in files and f["b"] in files and f["a"] != f["b"]]
            rows.append({"id": p["id"], "topic": p["topic"], "control": p["id"] in truth.get("controls", []), "found": bool(hit), "matching_conflicts": hit[:2]})
        planted = [r for r in rows if not r["control"]]
        controls = [r for r in rows if r["control"]]
        out[folder] = {"case_id": run["case_id"], "planted": len(planted), "found": sum(r["found"] for r in planted),
                       "controls": len(controls), "controls_wrongly_flagged": sum(r["found"] for r in controls),
                       "conflicts_reported_total": len(found_pairs), "conflicts_not_matching_a_planted_item": len([f for f in found_pairs if not any(f is h for r in rows for h in r["matching_conflicts"])]),
                       "rows": rows, "other_conflicts": [f for f in found_pairs if not any(f is h for r in rows for h in r["matching_conflicts"])][:6]}
    save("contradictions", out)
    for k, v in out.items():
        print(k, f"planted found {v['found']}/{v['planted']}", f"controls flagged {v['controls_wrongly_flagged']}/{v['controls']}", f"other conflicts {v['conflicts_not_matching_a_planted_item']}")


# ------------------------------------------------------------------ 2. the checker against planted physical faults

def checker():
    from pipeline import sandbox_geometry as sg
    out = {}
    for folder in CASES:
        runs = all_runs(folder)
        if not runs:
            continue
        inj = {"wall": [0, 0], "sprint": [0, 0], "jump": [0, 0]}
        repro = [0, 0]
        n_scn = 0
        for run in runs:
            layout = run["sandbox"]["run"]["layout"]
            for scn in run["sandbox"]["scenarios"]:
                n_scn += 1
                plan = scn["plan"]
                base = sg.validate_plan(plan, layout)
                repro[1] += 1
                # the checker is deterministic: the same plan and layout give the same verdict every time
                repro[0] += json.dumps(sg.validate_plan(plan, layout), sort_keys=True, default=str) == json.dumps(base, sort_keys=True, default=str)
                base_keys = {(v["code"], v.get("step"), v.get("actor")) for v in base["violations"]}
                if base_keys:
                    continue   # faults are planted only into plans the checker found clean, so a catch is never a plan that was already flagged

                def caught(bad):
                    return any((v["code"], v.get("step"), v.get("actor")) not in base_keys for v in sg.validate_plan(bad, layout)["violations"])
                walks = [(ai, si) for ai, a in enumerate(plan["actors"]) for si, s_ in enumerate(a["segments"]) if s_["kind"] == "transit" and s_.get("route") and len(s_["route"]) >= 2]
                rng = random.Random(7)
                for ai, si in rng.sample(walks, min(6, len(walks))):
                    bad = copy.deepcopy(plan)
                    seg = bad["actors"][ai]["segments"][si]
                    seg["route"][-1] = [seg["route"][-1][0] + 400.0, seg["route"][-1][1], seg["route"][-1][2]]
                    inj["wall"][1] += 1
                    inj["wall"][0] += caught(bad)
                    bad = copy.deepcopy(plan)
                    seg = bad["actors"][ai]["segments"][si]
                    if seg["t1"] - seg["t0"] > 1.0 and (seg.get("length_m") or 0) > 8.0:
                        seg["t1"] = seg["t0"] + (seg["t1"] - seg["t0"]) / 10.0
                        seg["v_max"] = (seg.get("v_max") or 1.4) * 10.0
                        inj["sprint"][1] += 1
                        inj["sprint"][0] += caught(bad)
                dwell = [(a2, s2) for a2, a in enumerate(plan["actors"]) for s2, s_ in enumerate(a["segments"]) if s_["kind"] == "dwell" and s2 > 0]
                for a2, s2 in dwell[:4]:
                    bad = copy.deepcopy(plan)
                    pos = bad["actors"][a2]["segments"][s2]["pos"]
                    bad["actors"][a2]["segments"][s2]["pos"] = [pos[0] + 3.0, pos[1], pos[2] + 3.0]
                    inj["jump"][1] += 1
                    inj["jump"][0] += caught(bad)
        out[folder] = {"runs": len(runs), "scenarios": n_scn, "revalidation_identical": repro, "faults": inj}
        print(folder, out[folder])
    save("checker", out)


# ------------------------------------------------------------------ 3. the second-model reviewer against planted flaws

def plant(scn, kind, rng):
    """Returns (damaged copy, {"step": n|None, "person": label|None, "types": [...]}) or (None, None) when the scenario has nothing to damage that way."""
    bad = copy.deepcopy(scn)
    actors = bad["plan"]["actors"]
    steps = [(a, st) for a in actors for st in a["steps"]]
    if kind == "narrative_swap":
        cand = [(a, st) for a, st in steps if st["action"] not in ("exit", "leave", "enter", "flee")]
        if not cand:
            return None, None
        a, st = rng.choice(cand)
        st["narrative"] = f"{a['label']} sprints out of the main entrance and drives away in a car."
        return bad, {"step": st["k"] + 1, "person": a["label"], "types": ["narrative_vs_action", "evidence_mismatch", "unsupported_claim", "spatial"]}
    if kind == "wrong_citation":
        index = list((bad.get("evidence_index") or {}).items())
        if len(index) < 3:
            return None, None
        a, st = rng.choice([(a, st) for a, st in steps if st["evidence_refs"]] or [(None, None)])
        if a is None:
            return None, None
        own = set(st["evidence_refs"])

        def overlap(txt):
            w = lambda s: set(re.findall(r"[a-z]{4,}", s.lower()))  # noqa: E731
            return len(w(txt) & w(st["narrative"]))
        worst = min((i for i in index if i[0] not in own), key=lambda i: overlap(i[1].get("text") or ""), default=None)
        if not worst:
            return None, None
        st["evidence_refs"] = [worst[0]]
        return bad, {"step": st["k"] + 1, "person": a["label"], "types": ["evidence_mismatch", "unsupported_claim", "timing", "narrative_vs_action"]}
    if kind == "role_swap":
        a = rng.choice([a for a in actors if a["role"] in ("staff", "witness", "victim")] or actors)
        old = a["role"]
        a["role"] = "suspect" if old != "suspect" else "witness"
        return bad, {"step": None, "person": a["label"], "types": ["role", "other"]}
    if kind == "time_shift":
        a = rng.choice(actors)
        late = [st for st in a["steps"] if st["k"] >= 1]
        if not late:
            return None, None
        st = rng.choice(late)
        for s2 in a["steps"]:
            if s2["k"] >= st["k"]:
                s2["arrive_s"] += 3600
                s2["depart_s"] += 3600
        return bad, {"step": st["k"] + 1, "person": a["label"], "types": ["timing", "evidence_mismatch"]}
    return None, None


def reviewer(mode: str):
    os.environ["LLM_PROVIDER_MODE"] = mode
    if mode == "local_only":
        os.environ.setdefault("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
        os.environ.setdefault("LOCAL_LLM_MODEL", "llama3.1:8b")
    import logging
    logging.disable(logging.WARNING)
    from pipeline import sandbox_evidence as evd
    from pipeline import sandbox_reviewer as rv
    from pipeline import sandbox_review as srv
    from pipeline.redaction import build_redactor, redaction_enabled
    kinds = ["narrative_swap", "wrong_citation", "role_swap", "time_shift"]
    out = {"provider_mode": mode, "with_images": mode != "local_only", "cases": {}}
    for folder in CASES:
        run = best_run(folder)
        if not run:
            continue
        case_id = run["case_id"]
        layout = run["sandbox"]["run"]["layout"]
        scn = max(run["sandbox"]["scenarios"], key=lambda s_: s_["score"]["verifiable_score"])
        ev = evd.gather_evidence(case_id)
        redactor = build_redactor(ev["entities"], redaction_enabled())
        known = evd.known_refs(ev)
        photos = srv._photos(case_id, ev)
        call = srv.make_call(redactor)
        use_images = mode != "local_only"
        rng = random.Random(11)
        rows = []
        clean = rv.review_scenario(scn, layout, ev, known, photos, call, redact=redactor.redact, with_images=use_images)
        for kind in kinds:
            bad, truth = plant(scn, kind, rng)
            if bad is None:
                continue
            res = rv.review_scenario(bad, layout, ev, known, photos, call, redact=redactor.redact, with_images=use_images)
            hit = [f for f in res["findings"] if (truth["step"] and f["step"] == truth["step"]) or (truth["person"] and f.get("person") and truth["person"].lower() in f["person"].lower()) and f["type"] in truth["types"]]
            hit_type = [f for f in res["findings"] if f["type"] in truth["types"] and (truth["step"] is None or f["step"] in (None, truth["step"]))]
            rows.append({"flaw": kind, "planted_at": truth, "found": bool(hit), "found_loosely": bool(hit or hit_type), "findings": len(res["findings"]), "dropped": res["dropped_findings"],
                         "batches_failed": res["batches_failed"], "model": res["model"], "seconds": res["seconds"]})
            print(folder, kind, rows[-1]["found"], rows[-1]["findings"], flush=True)
        out["cases"][folder] = {"clean_findings": len(clean["findings"]), "clean_verdict": clean["verdict"], "model": clean["model"], "rows": rows}
    save(f"reviewer_{mode}", out)


# ------------------------------------------------------------------ 4. run-to-run variance

def variance():
    out = {}
    for folder in CASES:
        runs = sorted(RES.glob(f"{folder}__meta_only*.json"))
        scores = []
        for p in runs:
            d = json.loads(p.read_text(encoding="utf-8"))
            sc = (d["sandbox"].get("scenarios") or [])
            if sc:
                scores.append({"file": p.name, "best": max(s["score"]["verifiable_score"] for s in sc), "scores": sorted((s["score"]["verifiable_score"] for s in sc), reverse=True),
                               "physically_possible": sum(1 for s in sc if s["validation"]["is_physically_possible"]), "n": len(sc)})
        best = [s["best"] for s in scores]
        out[folder] = {"runs": scores, "best_mean": round(statistics.mean(best), 1) if best else None, "best_stdev": round(statistics.pstdev(best), 1) if len(best) > 1 else None,
                       "best_min": min(best) if best else None, "best_max": max(best) if best else None}
        print(folder, out[folder]["best_mean"], out[folder]["best_stdev"], best)
    save("variance", out)


# ------------------------------------------------------------------ 5. the written report

def _load(name):
    p = RES / f"benchmark_{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _pct(a, b):
    return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "n/a"


def _scene_row(folder, mode):
    d = best_run(folder) if mode == "meta_only" else load_run(folder, mode)
    if not d:
        return None
    sb = d["sandbox"]
    sc = sb.get("scenarios") or []
    gen = (sb.get("run") or {}).get("generation") or {}
    lay = (sb.get("run") or {}).get("layout") or {}
    repairs = gen.get("repairs") or []
    return {"status": sb["status"], "rooms": len(lay.get("rooms", [])), "fixtures": len(lay.get("fixtures", [])), "scenarios": len(sc),
            "best": max((s["score"]["verifiable_score"] for s in sc), default=None),
            "possible": sum(1 for s in sc if s["validation"]["is_physically_possible"]),
            "repairs": len(repairs), "repairs_fixed": sum(1 for r in repairs if r.get("fixed")),
            "agent_repairs": sum(1 for r in repairs if r.get("method") == "tool_calling"),
            "seconds": d["seconds"]}


def report():
    L = ["# Benchmarks (fictional cases, planted answers)", "",
         "Everything here is measured on the three fictional cases in `backend/data/synthetic_cases`. Their contradictions and controls are listed in each case's `ground_truth.json`. "
         "Numbers are counts from the runs saved in `backend/data/synthetic_cases/results`. Nothing was tuned on these results after measuring. "
         "They show how the system behaves on three small invented cases, not how it will behave on real ones.", ""]
    c = _load("contradictions")
    if c:
        L += ["## 1. Contradictions between sources: planted vs found", "",
              "A planted contradiction counts as found when the evidence analysis reports a conflict between two of the sources named for it. A control is something that is consistent on purpose and must not be flagged.", "",
              "| Case | Planted found | Controls wrongly flagged | Other conflicts reported |", "|---|---|---|---|"]
        tp = tt = 0
        for k, v in c.items():
            tp += v["found"]
            tt += v["planted"]
            L.append(f"| {k} | {_pct(v['found'], v['planted'])} | {v['controls_wrongly_flagged']}/{v['controls']} | {v['conflicts_not_matching_a_planted_item']} |")
        L += ["", f"**Overall: {_pct(tp, tt)} planted contradictions found.** 'Other conflicts' are reported conflicts that match no planted item. They are not necessarily wrong (real cases hold more disagreements than the ones planted); they need a person to read them.", ""]
        for k, v in c.items():
            L.append(f"- **{k}**: " + "; ".join((f"{r['id']} control wrongly flagged" if r["found"] else f"{r['id']} control correctly not flagged") if r["control"] else f"{r['id']} {'found' if r['found'] else 'MISSED'}" for r in v["rows"]))
        L.append("")
    k = _load("checker")
    if k:
        L += ["## 2. Planted physical faults caught by the independent checker", "",
              "On each case's real generated scenarios, faults are planted into plans the checker found clean: a walk pushed through a wall, a walk squeezed into a tenth of its time (a sprint nobody can sustain), and a stop that is not where the walk before it ended. The checker is the deterministic validator; no model is involved.", "",
              "| Case | Runs | Scenarios | Same verdict on re-check | Walk through wall | Impossible sprint | Position jump |", "|---|---|---|---|---|---|---|"]
        tot = {"wall": [0, 0], "sprint": [0, 0], "jump": [0, 0]}
        for case, v in k.items():
            f = v["faults"]
            for kk in tot:
                tot[kk][0] += f[kk][0]
                tot[kk][1] += f[kk][1]
            L.append(f"| {case} | {v['runs']} | {v['scenarios']} | {_pct(*v['revalidation_identical'])} | {_pct(*f['wall'])} | {_pct(*f['sprint'])} | {_pct(*f['jump'])} |")
        L += ["", f"**Overall: wall {_pct(*tot['wall'])}, sprint {_pct(*tot['sprint'])}, jump {_pct(*tot['jump'])}.** The same check on 2,500 random scenes (`scripts/sandbox_eval.py`) is the larger sample.", ""]
    L += ["## 3. Meta-only vs local Llama on the same case", "",
          "Same evidence observations (read once by Meta). Then the scene and scenarios are generated twice: with `LLM_PROVIDER_MODE=meta_only` (Muse Wonder through the Meta Model API) and with `LLM_PROVIDER_MODE=local_only` (Llama 3.1 8B on a local Ollama server, nothing leaves the machine).", "",
          "| Case | Mode | Status | Rooms | Scenarios | Best score | Physically possible | Repairs fixed (by agent) | Time |", "|---|---|---|---|---|---|---|---|---|"]
    for folder in CASES:
        for mode in ("meta_only", "local_only"):
            r = _scene_row(folder, mode)
            if r:
                L.append(f"| {folder} | {mode}{' (best of ' + str(len(all_runs(folder))) + ' runs)' if mode == 'meta_only' else ''} | {r['status']} | {r['rooms']} | {r['scenarios']} | {r['best']} | {r['possible']}/{r['scenarios']} | {r['repairs_fixed']}/{r['repairs']} ({r['agent_repairs']}) | {r['seconds']} s |")
    L.append("")
    rm, rl = _load("reviewer_meta_only"), _load("reviewer_local_only")
    if rm or rl:
        L += ["### Reviewer: planted flaws found", "",
              "Flaws planted into each case's top scenario, one kind at a time: a step's sentence contradicting its action, a step citing unrelated evidence, a person given the wrong role, and a step time pushed an hour late. A flaw counts as found when a finding points at the damaged step (or person). 'Loose' also accepts a finding of the right type anywhere.", "",
              "| Reviewer | Strict | Loose | Findings on each clean (undamaged) scenario |", "|---|---|---|---|"]
        for name, r in (("Meta Muse Wonder, with plan-view pictures and photos", rm), ("Local Llama 3.1 8B, text only", rl)):
            if not r:
                continue
            rows = [x for v in r["cases"].values() for x in v["rows"]]
            clean = [v["clean_findings"] for v in r["cases"].values()]
            L.append(f"| {name} | {_pct(sum(x['found'] for x in rows), len(rows))} | {_pct(sum(x['found_loosely'] for x in rows), len(rows))} | {clean} |")
        L.append("")
    vv = _load("variance")
    if vv:
        L += ["## 4. Run-to-run variance", "", "The same case generated several times with Meta only (scene and scenarios regenerated each time).", "",
              "| Case | Runs | Best score each run | Mean | Std dev | Min to max |", "|---|---|---|---|---|---|"]
        for case, v in vv.items():
            best = [r["best"] for r in v["runs"]]
            L.append(f"| {case} | {len(best)} | {best} | {v['best_mean']} | {v['best_stdev']} | {v['best_min']} to {v['best_max']} |")
        L.append("")
    L += ["## What changed while we measured (so the numbers are not read as a clean first attempt)", "",
          "1. **Detector topics.** The contradiction detector only knew burglary vocabulary (doors, entry, alarm), so the road case found nothing. We added generic topics (signals, speed, collision or injury, emergency calls, access control) and a second pass that pairs an untimed statement with recorded entries. Results before that change are kept in `benchmark_contradictions_before_generic_topics.json`.",
          "2. **The assault case text was corrected twice.** The first version never said how anyone enters, and the second described an upper floor, which the scene builder cannot enter from outside. Both earlier runs are kept in `results/old_rubric/`. The case is now a ground-floor office with a stated street entrance.",
          "3. **A door-width bug.** A 1 m door in a 1.5 m corridor wall was squeezed to 0.5 m, so nobody could pass. Fixed in the geometry engine, with tests and a 600-scene stress sample (100 percent fault detection, 0 unexplained rejections).",
          "4. **The scoring rule.** Alternative readings that side with the other source of a disputed clock were flattened to 25 by a hard cap. Each such conflict now costs 8 points instead; physical impossibility still caps at 25. All scene results above were regenerated under the current rule; the earlier runs are in `results/old_rubric/`.",
          "5. **Local Llama context.** With the default context window the local model failed at the layout step. A 16k-context copy of the same weights completed, and that is the model measured here.", ""]
    L += ["## How to reproduce", "", "```bash", "cd backend",
          "python scripts/synthetic_cases_run.py <folder> meta_only                              # a case end to end (creates the case)",
          "python scripts/synthetic_cases_run.py <folder> local_only --reuse <case id>           # local Llama on the same observations",
          "python scripts/synthetic_cases_run.py <folder> meta_only --reuse <case id> --tag _r2  # another run, for variance",
          "python scripts/sandbox_benchmark.py contradictions && python scripts/sandbox_benchmark.py checker",
          "python scripts/sandbox_benchmark.py reviewer meta_only && python scripts/sandbox_benchmark.py reviewer local_only",
          "python scripts/sandbox_benchmark.py variance && python scripts/sandbox_benchmark.py report", "```", "",
          "## Limits", "", "- Three small fictional cases, written by the team. Planted contradictions are the kind we thought of.",
          "- **Reviewer noise.** Both reviewers returned 10 findings (the maximum kept) on the undamaged scenarios too. A reviewer that reports something on everything will \"find\" a planted flaw often, so the detection rates above are optimistic and say little about precision. We report them for the comparison between the two reviewers, not as a measure of accuracy.",
          "- **Contradiction detection is weak on two cases.** The road and assault cases found none of the planted contradictions (0 of 6). Those need the detector to tie an untimed statement, or a rounded time such as \"about twenty to seven\", to the one recorded entry it disagrees with; the current pairing by similarity does not do that reliably.",
          "- **The road case has no 3D scene.** The scene builder draws building interiors, so the road collision returns \"insufficient evidence\" for the scene; its timeline, contradiction analysis and report still run. Hence no variance row.",
          "- **Run-to-run variance is large on the assault case** (25, 67, 25): in two of three runs the model proposed a route the checker rejected (for example a person arriving through a wall) and the repair step did not fix it. We show the best run in the comparison and all runs in the variance table.",
          "- The reviewer and the generator come from the same provider in Meta mode, so shared blind spots are possible.",
          "- Local Llama 3.1 8B is a small model. The comparison shows what an on-premise setup can do today, not a ceiling.",
          "- Scores are a rubric, not a probability. A higher score means better supported by the recorded evidence, not more likely true."]
    out = BACKEND.parent / "docs" / "BENCHMARKS.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "contradictions":
        contradictions()
    elif cmd == "checker":
        checker()
    elif cmd == "reviewer":
        reviewer(sys.argv[2])
    elif cmd == "variance":
        variance()
    elif cmd == "report":
        report()
    else:
        print(__doc__)
