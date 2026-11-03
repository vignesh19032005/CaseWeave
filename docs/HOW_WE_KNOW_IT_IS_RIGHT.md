# How we know it is right (and where it is not)

CaseWeave never asks a language model whether a scenario is possible. A model reads and proposes. Code checks. Then we measure the checkers themselves, on fictional cases whose answers we planted.

## 1. The model cannot invent geometry

- The model returns **sizes and relations** (a room about 8 m by 6 m, a counter along the north wall, a door between two rooms), never coordinates.
- A deterministic engine (`backend/pipeline/sandbox_geometry.py`) builds the walls, doors, floors and furniture from those, fits furniture inside rooms, and records for every size whether it was **stated** in the evidence, **inferred**, or **assumed**. Assumed things are drawn plainly with a red outline.
- Same input gives the same scene and the same plan. `python scripts/sandbox_eval.py` rebuilds random scenes twice and compares them.

## 2. Every scenario is checked by code that is separate from the planner

For each scenario the engine plans real routes around walls and furniture, opens, forces or locks doors at the right times, applies walking speeds, checks hand-overs and who can see whom, and puts every person on one clock taken from the evidence. A **separate validator** then re-checks the finished plan from scratch. If it finds a wall walked through, an impossible sprint, a jump in position, or a locked door passed, the scenario is flagged or rejected. The model is told the rules, but it is not the judge.

We test the validator by **planting faults** in plans that were consistent and counting how many it catches (walk through a wall, sprint nobody can sustain, a jump between positions). Results: [docs/BENCHMARKS.md](BENCHMARKS.md).

## 3. The tool-calling repair loop keeps the checker's answer

When a scenario has fixable problems, a Meta model repairs it **as an agent with a tool**: it calls `check_scenario` (our validator), reads what is still wrong, fixes, and checks again, up to four times. We keep the version the checker says has the fewest problems, not the last one the model wrote. If Meta tool calling is unavailable, a one-shot repair is used, and in `local_only` mode the agent is off.

## 4. Every claim cites evidence, and citations are checked

Each step cites the ids of the evidence that supports it. Citations to evidence that does not exist are removed, weak or disputed ones are flagged, and times the evidence does not state are marked. The score is a **documented rubric** (not a probability): contradicting evidence costs 8 points, an open question the evidence leaves unsettled costs 2.

## 5. A second model reviews, and its findings are checked too

A reviewer (Meta vision) sees plan-view pictures of the scene at every key moment and the case photographs. A finding is kept only if it points at a real step, picture or evidence id. It is shown as an opinion. "Nothing found" is not proof. We measure how many planted flaws it finds.

## 6. Contradictions between sources are measured against ground truth

Each fictional case has a `ground_truth.json` listing the contradictions we planted, plus controls that are consistent on purpose. [docs/BENCHMARKS.md](BENCHMARKS.md) reports how many were found, how many controls were wrongly flagged, and what else was flagged.

## 7. Records

Uploads are SHA-256 hashed and re-verified. Scene runs are immutable and versioned with content hashes. The audit log is hash-chained and keyed, and an export pack records the provider mode and model used for every call.

## What we cannot claim

- **Only fictional cases have been run.** It has not been validated on real cases with investigators.
- A scenario can pass every check and still be wrong. Passing means *consistent with the evidence and physics we model*, nothing more.
- The reviewer is the same model family as the generator, so shared blind spots are possible.
- Photo readings and boxes are inferred and never used for sizes. Sound, light, injuries changing speed, people blocking each other, vehicles driving, and windows are not modelled.
- Legal summaries are paraphrases. They are not legal advice and are not part of the demo.

## Reproduce it

```bash
cd backend
MYSQL_DATABASE=caseweave_test python -m pytest tests -q          # the test suite (needs a throwaway test database)
python scripts/sandbox_eval.py 2500                              # determinism, planted faults, false alarms on 2,500 random scenes
python scripts/synthetic_cases_run.py <folder> meta_only         # run a fictional case end to end
python scripts/sandbox_benchmark.py contradictions|checker|reviewer meta_only|reviewer local_only|variance|report
```
