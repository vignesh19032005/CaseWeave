"""Runs a synthetic demonstration case through the real pipeline, in this process, against the configured database.

  python scripts/synthetic_cases_run.py <folder> <meta_only|local_only|auto> [--reuse CASE_ID] [--no-review]

Without --reuse it creates a new case, uploads every evidence file through the real upload route, runs the analysis stages
(observations, timeline, discrepancies, entities), then generates the scene and the scenarios, then runs the second-model review.
With --reuse it skips the upload and analysis and only generates a new scene for the same case, so two provider modes can be compared on identical observations.
Writes data/synthetic_cases/results/<folder>__<mode>.json with everything the benchmark and the demo need.
The cases are fictional, so nothing real is sent to any provider.
"""
import json
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

folder, mode = sys.argv[1], sys.argv[2]
reuse = sys.argv[sys.argv.index("--reuse") + 1] if "--reuse" in sys.argv else None
do_review = "--no-review" not in sys.argv
tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else ""
os.environ["LLM_PROVIDER_MODE"] = mode
if mode == "local_only":
    os.environ.setdefault("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    os.environ.setdefault("LOCAL_LLM_MODEL", "llama3.1:8b")

import logging  # noqa: E402
logging.disable(logging.WARNING)
from fastapi.testclient import TestClient  # noqa: E402
import api  # noqa: E402
import auth  # noqa: E402

api.limiter.enabled = False
api.app.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "U-SYN", "username": "synthetic-runner", "role": "admin"}
c = TestClient(api.app)

SRC = BACKEND / "data" / "synthetic_cases" / folder
OUT = BACKEND / "data" / "synthetic_cases" / "results"
OUT.mkdir(exist_ok=True)
t_all = time.time()

if reuse:
    case_id = reuse
else:
    title = "[SYNTHETIC] " + folder.replace("_", " ").title()
    case_id = c.post("/cases", json={"title": title}).json()["case_id"]
    for p in sorted(SRC.iterdir()):
        if p.name in ("ground_truth.json",) or p.suffix.lower() not in (".txt", ".json", ".png", ".jpg", ".pdf"):
            continue
        r = c.post(f"/cases/{case_id}/evidence", files={"file": (p.name, p.read_bytes())})
        print("upload", p.name, r.status_code, flush=True)
    import job_queue
    t0 = time.time()
    job_queue._run_process_job(case_id, None)
    print("analysis stages done in", round(time.time() - t0), "s", flush=True)

t0 = time.time()
g = c.post(f"/cases/{case_id}/sandbox/generate", json={"mode": "full"})
state = c.get(f"/cases/{case_id}/sandbox").json()
print("sandbox", g.status_code, state["status"], round(time.time() - t0), "s", flush=True)
review = None
if do_review and state.get("scenarios"):
    t0 = time.time()
    rv = c.post(f"/cases/{case_id}/sandbox/review")
    review = c.get(f"/cases/{case_id}/sandbox/review").json()
    print("review", rv.status_code, round(time.time() - t0), "s", flush=True)
conflicts = c.get(f"/cases/{case_id}/conflicts").json()
timeline = c.get(f"/cases/{case_id}/timeline").json()
result = {"folder": folder, "case_id": case_id, "provider_mode": mode, "seconds": round(time.time() - t_all),
          "sandbox": state, "review": review, "conflicts": conflicts, "timeline": timeline}
(OUT / f"{folder}__{mode}{tag}.json").write_text(json.dumps(result, default=str), encoding="utf-8")
sc = state.get("scenarios") or []
print(json.dumps({"case_id": case_id, "mode": mode, "status": state["status"], "failure": state.get("last_failure"),
                  "conflicts": len(conflicts) if isinstance(conflicts, list) else conflicts,
                  "scenarios": [(s["rank"], s["score"]["verifiable_score"], s["validation"]["is_physically_possible"]) for s in sc],
                  "seconds": result["seconds"]}), flush=True)
