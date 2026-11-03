# CaseWeave

### When accounts disagree, CaseWeave tests them against the evidence.

**Propose. Check. Replay. Review.** A Meta model proposes what could have happened. Deterministic code decides what is possible. A person confirms every finding.

Built by **Team AKASHI** for the **Meta AI Developer Hackathon** (Cerebral Valley), theme **Build for Your World**.

| | |
|---|---|
| Demo video (under 3 minutes) | https://youtu.be/GKYcaDvdH5U |
| How it works (diagram) | [docs/architecture.svg](docs/architecture.svg) |

![The model proposes, the code decides](docs/architecture.png)

> **Every case in this repository and demo is fictional.** CaseWeave is analysis support for investigators. It does not decide who is guilty, it does not identify people, and it is not legal advice. Every output is AI-drafted and must be confirmed by a person against the source evidence.

---

## Contents
[The problem](#the-problem) · [What it does](#what-it-does) · [Where Meta's models and tools are used](#where-metas-models-and-tools-are-used) · [Try it](#try-it-fictional-cases-included) · [Run it](#run-it) · [Tests](#tests-and-measurements) · [Responsible use](#responsible-use) · [Layout](#repository-layout) · [Licence](#licence)

## The problem

Investigators reconcile statements, device logs and photographs by hand, and a contradiction between two of them is easy to miss. India's own figures show the scale:

- **51,24,205** IPC and BNS cases were under investigation in 2024, of which police disposed of 35,21,488 and chargesheeted 25,40,668 (a 72.1% chargesheeting rate). That leaves about **16.0 lakh (roughly 31%) not disposed of by year end** (our arithmetic from the published totals). Source: NCRB, *Crime in India 2024*, national snapshot, the first edition under the new BNS.
- On staffing, the Home Ministry told the Rajya Sabha that **Delhi Police alone was short of 9,248 posts against 92,044 sanctioned** (30 November 2025, as reported by The Tribune).

Reading every source against every other source is slow and error-prone. A tool that does it consistently, with citations, can help.

## What it does

1. **Reads the evidence.** Statements, device logs, CCTV notes, examiner reports and photographs are hashed on upload and read by a Meta model into a table of observations.
2. **Finds contradictions between sources**, each pointing at both sides, with a prosecutor, defender and judge debate a person can read.
3. **Builds a walkable 3D scene.** A model proposes sizes and relations, never coordinates. A geometry engine builds walls, doors and furniture, and marks every size *stated*, *inferred* or *assumed*. Assumed things stay plain with a red outline.
4. **Proposes several different scenarios**, each citing the evidence behind every step and scored by a documented rubric (a ranking of evidence support, **not** a probability).
5. **Checks every scenario with code.** Routes around walls and furniture, locked and forced doors, walking speeds, hand-overs, line of sight and one shared clock. An independent validator re-checks the result. Impossible plans are rejected by code, not by opinion.
6. **Repairs flawed plans as an agent.** A Meta model calls our checker as a tool, fixes, and re-checks. We keep whichever version the checker prefers.
7. **Shows who could see whom.** Camera and witness view cones stay calm until someone is in view, then turn red.
8. **Reviews with a second model** that sees plan-view pictures at every key moment and the case photographs. Its findings must cite a real step, picture or evidence id or they are dropped. It is an opinion, never proof.
9. **Exports** a formatted report and a printable PDF, with an audit trail (hash-chained, who did what and when) and the limits stated.

## Where Meta's models and tools are used

| Use | Meta component | Why it matters |
|---|---|---|
| Reading every evidence item, proposing the layout and several scenarios | **Muse Wonder** via the Meta Model API (`/v1/responses`) | The model reads and proposes. It never emits coordinates. |
| Reading case photographs into a short, checked list of what is visible | **Muse Wonder vision** | Qualitative only, marked *inferred*, never used for sizes. |
| Finding the scene's objects in the case photographs (boxes drawn on the photo) | **SAM 3.1** | Boxes are filtered, marked inferred, hashed and audited. |
| A second, independent review with plan-view pictures | **Muse Wonder multi-image vision** | Findings must cite something real or are dropped. |
| Repairing a scenario as an agent that calls our validator as a tool | **Meta Model API function calling** | The model proposes, our checker decides. |
| Running the pipeline with nothing leaving the building | **Llama 3.1 8B** (open weights) via Ollama | `LLM_PROVIDER_MODE=local_only`, measured against Meta-only below. |

Provider order is Meta first, then a local Llama server if configured, then fallbacks. `LLM_PROVIDER_MODE` is `auto`, `meta_only` or `local_only`, and the screen shows which was used. In `local_only` mode the tool-calling repair is switched off.

## Try it (fictional cases included)

Four fictional cases are in [backend/data/synthetic_cases](backend/data/synthetic_cases), each with different kinds of evidence and planted contradictions listed in its `ground_truth.json`:

| Case | Evidence types |
|---|---|
| Night burglary of a warehouse | alarm log, door-access log, CCTV log, two statements, examiner report, floor diagram |
| Office assault | emergency-call transcript, access-control log, CCTV log, medical note, three statements |
| Pharmacy burglary with photographs | alarm log, CCTV log, examiner report, two statements, four photographs (photo readings and SAM boxes) |
| Two-vehicle collision | telematics, signal log, dashcam transcript, three statements (analysis only; the 3D builder draws building interiors, not roads) |

```bash
cd backend
python scripts/synthetic_cases_run.py burglary_warehouse meta_only    # creates the case and runs the whole pipeline
```

## Run it

Requires Python 3.11, Node 20, Docker, and a Meta Model API key. For on-premise mode also install [Ollama](https://ollama.com) with `llama3.1:8b`.

```bash
cp backend/.env.example backend/.env      # set META_API_KEY and the MYSQL_* values
export MYSQL_ROOT_PASSWORD=... MYSQL_PASSWORD=...
pip install -r backend/requirements.txt
./run_all.sh                               # Windows: run_all.bat
```

This starts MySQL and Redis in Docker (bound to this machine only), the API on `127.0.0.1:8010`, the worker, and the web app on `http://localhost:3000`. Set `CASEWEAVE_ADMIN_PASSWORD` to choose the first admin password; otherwise the account starts on a shipped default and is forced to choose a new one at first sign-in.

**Local Llama:** long case prompts need a larger context window than Ollama's default. Create a 16k copy (`PARAMETER num_ctx 16384`) and set `LOCAL_LLM_MODEL` to it. See the comment in `backend/.env.example`.

Nothing is hardcoded to one case. Secrets live in `backend/.env` or the OS keyring and are never committed.

## Tests and measurements

```bash
cd backend
MYSQL_DATABASE=caseweave_test python -m pytest tests -q   # 585 tests, needs a throwaway test database
python scripts/sandbox_eval.py 2500                       # random scenes: determinism, planted faults, false alarms
cd ../frontend && npx tsc --noEmit && npx eslint .
```

The backend suite refuses to run against a database whose name does not contain `test`.

## Responsible use

- Scenarios are **possibilities consistent with the evidence**, not findings of fact. A person confirms everything against the source evidence.
- Photo readings and boxes are inferred and are never used for measurements.
- Where the evidence is silent, the scene says *assumed* and draws it plainly.
- The bundled legal reference summaries are shown only as an AI draft. They are not legal advice.
- It does not identify people or score behaviour. Use it only to test accounts of an incident against recorded evidence.

## Repository layout

```
backend/              FastAPI API, pipeline stages, geometry engine, validator, reviewer, tests
  pipeline/sandbox*.py     layout, scenarios, checker, repair agent, review, photo links
  data/synthetic_cases/    four fictional demonstration cases
  scripts/                 evaluation and case-runner scripts
frontend/             Next.js 16 and React Three Fiber web app (the 3D player is in app/scene)
docs/                 architecture diagram and pipeline notes
```

Notes on the full pipeline stages are in [docs/PIPELINE_STAGES.md](docs/PIPELINE_STAGES.md).

## Licence

MIT, see [LICENSE](LICENSE). Third-party 3D models are CC BY 4.0 from the Khronos glTF Sample Assets (required attribution: *Chair*, (c) 2021 Wayfair; *Milk Truck* and *Cesium Man*, (c) 2017 Cesium, all CC BY 4.0, used unmodified).
