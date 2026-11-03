# Benchmarks (fictional cases, planted answers)

Everything here is measured on the three fictional cases in `backend/data/synthetic_cases`. Their contradictions and controls are listed in each case's `ground_truth.json`. Numbers are counts from the runs saved in `backend/data/synthetic_cases/results`. Nothing was tuned on these results after measuring. They show how the system behaves on three small invented cases, not how it will behave on real ones.

## 1. Contradictions between sources: planted vs found

A planted contradiction counts as found when the evidence analysis reports a conflict between two of the sources named for it. A control is something that is consistent on purpose and must not be flagged.

| Case | Planted found | Controls wrongly flagged | Other conflicts reported |
|---|---|---|---|
| burglary_warehouse | 2/2 (100%) | 0/1 | 1 |
| road_accident_junction | 0/3 (0%) | 0/0 | 2 |
| indoor_assault_office | 0/3 (0%) | 0/0 | 0 |

**Overall: 2/8 (25%) planted contradictions found.** 'Other conflicts' are reported conflicts that match no planted item. They are not necessarily wrong (real cases hold more disagreements than the ones planted); they need a person to read them.

- **burglary_warehouse**: BURG-C1 found; BURG-C2 found; BURG-C3 control correctly not flagged
- **road_accident_junction**: RTC-C1 MISSED; RTC-C2 MISSED; RTC-C3 MISSED
- **indoor_assault_office**: ASLT-C1 MISSED; ASLT-C2 MISSED; ASLT-C3 MISSED

## 2. Planted physical faults caught by the independent checker

On each case's real generated scenarios, faults are planted into plans the checker found clean: a walk pushed through a wall, a walk squeezed into a tenth of its time (a sprint nobody can sustain), and a stop that is not where the walk before it ended. The checker is the deterministic validator; no model is involved.

| Case | Runs | Scenarios | Same verdict on re-check | Walk through wall | Impossible sprint | Position jump |
|---|---|---|---|---|---|---|
| burglary_warehouse | 3 | 9 | 9/9 (100%) | 54/54 (100%) | 29/29 (100%) | 36/36 (100%) |
| indoor_assault_office | 3 | 9 | 9/9 (100%) | 18/18 (100%) | n/a | 12/12 (100%) |

**Overall: wall 72/72 (100%), sprint 29/29 (100%), jump 48/48 (100%).** The same check on 2,500 random scenes (`scripts/sandbox_eval.py`) is the larger sample.

## 3. Meta-only vs local Llama on the same case

Same evidence observations (read once by Meta). Then the scene and scenarios are generated twice: with `LLM_PROVIDER_MODE=meta_only` (Muse Wonder through the Meta Model API) and with `LLM_PROVIDER_MODE=local_only` (Llama 3.1 8B on a local Ollama server, nothing leaves the machine).

| Case | Mode | Status | Rooms | Scenarios | Best score | Physically possible | Repairs fixed (by agent) | Time |
|---|---|---|---|---|---|---|---|---|
| burglary_warehouse | meta_only (best of 3 runs) | ready | 3 | 3 | 74 | 3/3 | 1/1 (1) | 204 s |
| burglary_warehouse | local_only | ready | 4 | 3 | 25 | 0/3 | 2/4 (0) | 360 s |
| indoor_assault_office | meta_only (best of 3 runs) | ready | 5 | 3 | 67 | 3/3 | 0/0 (0) | 193 s |
| indoor_assault_office | local_only | ready | 4 | 3 | 25 | 0/3 | 0/4 (0) | 245 s |

### Reviewer: planted flaws found

Flaws planted into each case's top scenario, one kind at a time: a step's sentence contradicting its action, a step citing unrelated evidence, a person given the wrong role, and a step time pushed an hour late. A flaw counts as found when a finding points at the damaged step (or person). 'Loose' also accepts a finding of the right type anywhere.

| Reviewer | Strict | Loose | Findings on each clean (undamaged) scenario |
|---|---|---|---|
| Meta Muse Wonder, with plan-view pictures and photos | 6/8 (75%) | 6/8 (75%) | [10, 10] |
| Local Llama 3.1 8B, text only | 5/8 (62%) | 6/8 (75%) | [10, 10] |

## 4. Run-to-run variance

The same case generated several times with Meta only (scene and scenarios regenerated each time).

| Case | Runs | Best score each run | Mean | Std dev | Min to max |
|---|---|---|---|---|---|
| burglary_warehouse | 3 | [71, 74, 72] | 72.3 | 1.2 | 71 to 74 |
| road_accident_junction | 0 | [] | None | None | None to None |
| indoor_assault_office | 3 | [25, 67, 25] | 39 | 19.8 | 25 to 67 |

## What changed while we measured (so the numbers are not read as a clean first attempt)

1. **Detector topics.** The contradiction detector only knew burglary vocabulary (doors, entry, alarm), so the road case found nothing. We added generic topics (signals, speed, collision or injury, emergency calls, access control) and a second pass that pairs an untimed statement with recorded entries. Results before that change are kept in `benchmark_contradictions_before_generic_topics.json`.
2. **The assault case text was corrected twice.** The first version never said how anyone enters, and the second described an upper floor, which the scene builder cannot enter from outside. Both earlier runs are kept in `results/old_rubric/`. The case is now a ground-floor office with a stated street entrance.
3. **A door-width bug.** A 1 m door in a 1.5 m corridor wall was squeezed to 0.5 m, so nobody could pass. Fixed in the geometry engine, with tests and a 600-scene stress sample (100 percent fault detection, 0 unexplained rejections).
4. **The scoring rule.** Alternative readings that side with the other source of a disputed clock were flattened to 25 by a hard cap. Each such conflict now costs 8 points instead; physical impossibility still caps at 25. All scene results above were regenerated under the current rule; the earlier runs are in `results/old_rubric/`.
5. **Local Llama context.** With the default context window the local model failed at the layout step. A 16k-context copy of the same weights completed, and that is the model measured here.

## How to reproduce

```bash
cd backend
python scripts/synthetic_cases_run.py <folder> meta_only                              # a case end to end (creates the case)
python scripts/synthetic_cases_run.py <folder> local_only --reuse <case id>           # local Llama on the same observations
python scripts/synthetic_cases_run.py <folder> meta_only --reuse <case id> --tag _r2  # another run, for variance
python scripts/sandbox_benchmark.py contradictions && python scripts/sandbox_benchmark.py checker
python scripts/sandbox_benchmark.py reviewer meta_only && python scripts/sandbox_benchmark.py reviewer local_only
python scripts/sandbox_benchmark.py variance && python scripts/sandbox_benchmark.py report
```

## Limits

- Three small fictional cases, written by the team. Planted contradictions are the kind we thought of.
- **Reviewer noise.** Both reviewers returned 10 findings (the maximum kept) on the undamaged scenarios too. A reviewer that reports something on everything will "find" a planted flaw often, so the detection rates above are optimistic and say little about precision. We report them for the comparison between the two reviewers, not as a measure of accuracy.
- **Contradiction detection is weak on two cases.** The road and assault cases found none of the planted contradictions (0 of 6). Those need the detector to tie an untimed statement, or a rounded time such as "about twenty to seven", to the one recorded entry it disagrees with; the current pairing by similarity does not do that reliably.
- **The road case has no 3D scene.** The scene builder draws building interiors, so the road collision returns "insufficient evidence" for the scene; its timeline, contradiction analysis and report still run. Hence no variance row.
- **Run-to-run variance is large on the assault case** (25, 67, 25): in two of three runs the model proposed a route the checker rejected (for example a person arriving through a wall) and the repair step did not fix it. We show the best run in the comparison and all runs in the variance table.
- The reviewer and the generator come from the same provider in Meta mode, so shared blind spots are possible.
- Local Llama 3.1 8B is a small model. The comparison shows what an on-premise setup can do today, not a ceiling.
- Scores are a rubric, not a probability. A higher score means better supported by the recorded evidence, not more likely true.
