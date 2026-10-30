# CaseWeave AI — Combined Pilot-Grade Build Plan

Supersedes the original 10-day hackathon-only plan and merges in the valuable
stages from the independent 18-stage roadmap. Reframed per explicit
direction: **build as if this ships to a real pilot department, not just a
demo booth** — but "minimal logging and audit-based," not full enterprise
security. That line matters, draw it precisely:

**What "pilot-grade minimal" means here — build these for real:**

- Real authentication (actual login, not a role dropdown) — simple JWT/session, not SSO/OAuth-federated IAM.
- Real authorization — role checks enforced on every endpoint, not just stored in a DB column.
- Real audit log — the hash-chained, tamper-evident `AuditEvent` chain already built, verified on every report export.
- Real evidence integrity — SHA-256 hash on upload, re-verified before any evidence is read or exported.

**What stays out, explicitly, even for a pilot:** encryption-at-rest key
management, penetration testing, formal compliance certification, SSO/multi-
org IAM, horizontal scaling/load balancing, disaster recovery. Those are
real deployment's job, not this build's — naming them here so nothing is
silently implied as done.

## Reality check on pace

Original plan assumed 10 calendar days for 11 stages. Actual: **6-7 stages built and verified live (not stubbed) in about half a day**, once Meta/Groq/ Gemini/HF API keys were in hand and the "no mock mode" constraint forced real wiring from the start. That changes the planning math — the bottleneck was never raw coding time, it was credential/access acquisition (Groq model  
access, Gemini model name deprecation, HF gated-repo approval). Replan around that: **budget stage work in hours, budget access/approval lead time in days**, and don't let weight downloads (SAM 3 / SAM 3D Objects, ~16GB  
combined) block everything else — they run in the background while other stages proceed.

---

## Current real build status

| # | Stage | Status |
|---|---|---|
| 0 | Foundation | **Done, verified live.** FastAPI (`api.py`) + Next.js frontend both running. SQLite. Hash-chained audit log, verified PASSED via `/cases/{id}/audit`. Local S3-equivalent object store (`storage.py`) — MinIO itself is blocked (gated Docker images since 2025), this is the disclosed substitute. |
| 1 | Media Extraction | **Built**, not yet exercised on a real file. `pipeline/extract.py`: PyMuPDF+Tesseract OCR fallback, ffmpeg frame/audio extraction, Groq Whisper transcription. |
| 2 | Observation Engine | **Done, verified live.** `pipeline/observe.py`. Real LLM calls, Meta→Groq→Gemini fallback chain actually exercised (Meta key absent, Groq model-access/token-budget/reasoning-effort bugs found and fixed). |
| 3 | Timeline Builder | **Done, verified.** `pipeline/timeline.py` + real HTML artifact `timeline_html.py`, plus a live React timeline in the Next.js dashboard. |
| 4 | Discrepancy Detection | **Done, verified live.** `pipeline/discrepancy.py`. Real LLM adjudication (heuristic candidate pairs + semantic LLM verdict), confirmed catching a genuine conflict; known non-determinism on the free model documented, not hidden. |
| 5 | Legal Retrieval | **Done, verified.** `pipeline/legal.py`. Real `all-MiniLM-L6-v2` embeddings + local persisted ChromaDB, cosine-space bug found and fixed, correct ranked results confirmed. |
| 6 | Procedural Scene Shell | **Done, verified live.** `pipeline/scene.py` + `/scene` page. Real LLM-generated Three.js JSX, compiled at runtime (Babel standalone) and rendered in an orbit-controllable React Three Fiber canvas. |
| 7 | Object Reconstruction | **Done, verified live, via the alternative path.** `pipeline/reconstruct.py`: same method as the buildgen reference project (vision-describes the object, writes procedural Three.js primitive geometry) — Muse Wonder vision call confirmed real, generated correct multi-part geometry for a toppled chair (cylinder legs, box seat, sphere casters, matching colors). Honest disclosure: approximation, not true mesh reconstruction. The self-hosted SAM 3D Objects path (real reconstruction) stays available as an alternate mode once weights finish downloading, but is no longer required to call Stage 7 done. |
| 8 | Segmentation | **Done, verified live.** Switched from the stuck self-hosted SAM 3 download to Meta's hosted SAM 3.1 via the same `/v1/responses` endpoint (model `sam-3.1`) — confirmed real box + pixel-accurate mask returned for "chair" and "cardboard box" prompts on real evidence photos. Self-hosted download no longer needed for this stage. |
| 9 | Scenario Comparison | **Done, verified live.** `pipeline/scenarios.py`. Real LLM call grounded in actual conflict content. |
| 10 | Report Export + Audit | **Done, verified.** `pipeline/report.py`. Real Markdown report, audit chain cryptographically verified PASSED in the output. |

Evidence photos staged and ready: 6 real photos (door entrance, toppled chair,
scattered papers, torn-open box, desk surfaces), cropped and stored in
`backend/data/case_cw001/photos/`, mapped to Stage 6-8 roles.

---

## Merged stage list (hackathon + roadmap, pilot-framed)

Stages 0-10 are unchanged from the table above — they stay the backbone.
The roadmap's genuinely valuable missing pieces are merged **directly into**
the existing stages or added as new numbered stages in sequence, not kept in
a separate "maybe later" bucket, because the ambition level just moved from
"demo" to "pilot."

### Stage 2 — upgrade: structured entity extraction

Add subject/action/location/time_claim fields (Pydantic-validated) to the
Observation schema, on top of the existing description/classification/
source/limitations fields. This is what unlocks Stage 11 below. Small
schema + prompt change, not a rewrite — `pipeline/observe.py`'s LLM call
already returns structured JSON, just needs a richer target schema.

### Stage 2.5 (new) — Evidence-grounded case chat

Separate from Stage 5's legal RAG: index the case's *own* uploaded evidence
in a second ChromaDB collection (same `pipeline/legal.py` pattern, reused,
not rebuilt) so an investigator can ask "where was Person A reportedly seen
at 8:30 PM?" and get a source-linked answer from the case's own
observations. New FastAPI endpoint, ~3-4 files, ~250 LOC.

### Stage 4 — upgrade: review-status workflow + evidence linking

Two additions to the existing discrepancy engine:

1. `review_status: confirmed|resolved|unresolved` on every `Conflict` row +

   a PATCH endpoint + a UI button — turns the conflict list from read-only
    into something an investigator works through.
2. Positive evidence links — extend the same candidate-pair/LLM-adjudication

   pattern to also label pairs `supports`/`related_to`, not just `conflicts`.
    Reuses `pipeline/discrepancy.py`'s existing machinery.

### Stage 11 (new) — Entity Resolution + Relationship Graph

Needs Stage 2's entity-extraction upgrade first. Dedup/alias-match entities
across evidence, render as an interactive graph (React Flow). This is the
single highest-value addition for a real pilot — it's what turns "a pile of
linked documents" into "an investigation map."

### Stage 9 — upgrade: generalize toward incident reconstruction

Stage 9's Scenario Comparison already generates alternative explanations per
conflict. Extend it to read the full timeline + entity graph + all conflicts
and produce one synthesized incident narrative with explicit unresolved
gaps — the roadmap's "Cross-Evidence Incident Reconstruction" idea, built as
a generalization of code that already exists rather than a new engine.

### Stage 12 (new) — Real auth + enforced RBAC

Upgrades Stage 0's role-stub to the "pilot-grade minimal" bar defined above:
actual login (JWT), actual per-endpoint role checks (investigator can
upload/view, reviewer can confirm/resolve conflicts, admin can export/manage
users). Not SSO, not multi-tenant — a real single-department login system,
nothing more.

**Explicitly still deferred, named so nothing drops silently:** task/lead
management (roadmap Stage 13), full multi-case/multi-org dashboard at scale
(roadmap Stage 15 beyond what Stage 11's graph gives), multi-agent
orchestration (roadmap Stage 16 — deliberately rejected, direct pipeline
calls are simpler and sufficient), formal multi-case evaluation harness
(roadmap Stage 17 — `tests/test_pipeline.py` already proves the pattern for
one case, scaling it to a curated multi-case set is real future work, not
urgent).

---

## Model Fallback Matrix

Unchanged from the original plan — still accurate, still the real fallback
chain in use (`backend/llm_client.py`).

| Stage | Task | Primary (Meta, via hosted API) | Secondary (free-tier API) | Tertiary (free-tier API) |
|---|---|---|---|---|
| 1 | Audio transcription | MMS via HF Inference API | Groq free tier — `whisper-large-v3` | AssemblyAI free tier |
| 2 | Observation extraction | Muse Spark via Meta Model API | Groq free tier — Llama 4 Scout/Maverick | Gemini Flash (non-Meta, disclose if used) |
| 4 | Discrepancy reasoning | Llama via Meta Model API | Groq free tier — Llama 3.3 70B | Gemini Flash (non-Meta) |
| 5 | Legal embeddings | Llama embeddings via HF Inference API | sentence-transformers MiniLM (local, free) — **this is what's actually in production use** | Cohere/Google embeddings (non-Meta) |
| 6-9 | Text generation (scene codegen, scenarios) | Llama/Muse Spark via Meta Model API | Groq free tier — Llama 3.3 70B | Gemini Flash (non-Meta) |
| 7 | 3D object reconstruction | **Procedural approximation via Muse Wonder (confirmed live) — primary now**; SAM 3D Objects self-hosted real reconstruction available as alternate mode | TripoSR via HF Inference | Hunyuan3D-2 HF Space |
| 8 | Segmentation | **SAM 3.1 via Meta Model API, hosted (confirmed live)** | SAM 2 via HF Inference | Roboflow free tier |

**Update: real Meta API key received and live (26 Oct 2026).** Confirmed
working via actual calls — text, structured JSON output, and vision (image
input) all tested successfully against real evidence. Real endpoint:
`https://api.meta.ai/v1/responses` with model `muse-wonder-1.0` (NOT
`api.llama.com/v1/chat/completions` as earlier assumed — that was a wrong
guess, corrected after testing). Full pipeline test suite: 22/22 passing
with Meta as primary, including Stage 4's discrepancy detection catching
the real conflict on this run (previously flaky on the free-tier fallback
— first evidence the paid model is more consistent, as Stage 22 predicted).
Groq/Gemini now genuinely idle as pure fallback, exactly as designed.

**Update: Stage 8 segmentation resolved.** Real endpoint found — same
`/v1/responses` endpoint, model `sam-3.1` (Meta's hosted SAM 3.1), no
separate path needed. Confirmed live: real box + pixel-accurate mask
returned for "chair" and "cardboard box" prompts on real evidence photos
(`pipeline/segment.py`). The stuck self-hosted SAM 3 download is no longer
needed for this stage and can be abandoned.

Still pending: the real endpoint path for Meta's hosted Transcribe
(speech-to-text) API — exists per Meta's own "Models at a glance" docs but
not yet confirmed. Once found, this could let Stage 1's audio transcription
run on Meta's hosted API directly instead of the Groq Whisper fallback.

**Stage 7 (SAM 3D Objects, single-image 3D reconstruction) has no Meta-
hosted equivalent** — checked against Meta's full models table, nothing
there produces 3D mesh/geometry output. Stays on the self-hosted path,
still mid-download, still the one stage without a hosted shortcut.

---

## Day-to-stage pacing (recalibrated)

Given actual velocity (6-7 core stages in half a day once keys were live),
the bottleneck is access/approval lead time, not coding:

| Day | Work |
|---|---|
| 0.5 (done) | Stages 0, 2, 3, 4, 5, 6, 9, 10 built and verified live |
| In progress | Stage 1 real-file exercise; Stage 7/8 weight downloads (background, resumable) |
| Next | Stage 2 entity-extraction upgrade, Stage 2.5 case chat, Stage 4 review-status + evidence-linking upgrade |
| Then | Stage 11 entity graph (needs Stage 2 upgrade first) |
| Then | Stage 9 generalization to incident reconstruction (needs Stage 11) |
| Then | Stage 12 real auth/RBAC |
| Buffer | Stage 7/8 real inference calls once weights finish + model output API inspected |

No fixed 10-day lockstep anymore — sequence by dependency, not by calendar
day. The only genuinely slow items are: SAM 3/SAM 3D Objects downloads
(~16GB, background), and any future Meta API key approval if one is sought.

---

## Pilot Readiness Gap & Next Steps (updated)

**What this build now actually proves, at pilot-grade minimal bar:**

- Cross-source evidence linking + traceability works end-to-end, verified live, not stubbed.
- Discrepancy detection catches real conflicts via live LLM reasoning, not hardcoded rules.
- Legal citations are source-grounded via real embeddings, not keyword tricks.
- Audit trail is real and cryptographically verified (hash-chain PASSED), not a placeholder field.
- Auth/RBAC, once Stage 12 lands, will be real login + enforced role checks — not a UI dropdown.

**What's still explicitly NOT done — required before any live case:**

| Gap | What real deployment needs |
|---|---|
| Encryption | At-rest key management, TLS termination hardening |
| Compliance | Formal legal sign-off on schema against BSA 2023/IT Act provisions |
| Pen testing | Independent security review before handling real case data |
| Validation | Testing against real (authorized, anonymized) casework, not just synthetic |
| Scale | SQLite/single-instance → multi-case, concurrent-load architecture |
| AI reliability | Confidence calibration, adversarial testing — the free-model non-determinism noted in Stage 4 needs resolving with a stronger/paid model before anything court-facing |

**Proposed next steps if a department is interested:** scoping workshop →
hardening phase (real encryption, compliance sign-off, pen test) → shadow
pilot on closed/past cases → limited live pilot with human override always
default. Same sequence as before — the minimal-but-real auth/audit work in
this plan shortens that hardening phase, it doesn't skip it.

---

## Final Combined Stage List (0-25, single source of truth)

Supersedes any earlier stage numbering/section. Status reflects real build
state as of this build session, not plan intent — "Done, verified live"
means actually run and checked (live LLM call, live HTTP request, or live
DB round-trip), not just code written.

| # | Stage | Status | Depends on | Tier |
|---|---|---|---|---|
| 0 | Foundation (FastAPI + Next.js + MySQL + hash-chained audit + object store) | **Done, verified live** — UI: login → Case Command Center → per-case Reconstruction Studio (Evidence Explorer / Studio / Conflict Analysis / Report tabs). Audit appends serialized per case (MySQL `GET_LOCK`) after a real chain fork was traced to concurrent writers; GET endpoints are now strictly read-only | — | Hackathon |
| 1 | Media Extraction (PDF/OCR/video/audio) | **Done, verified live** — real PDF generated and extracted via text layer; OCR fallback tested on a real photo | Stage 0 | Hackathon |
| 2 | Observation Engine (LLM-structured claims, source-linked) | **Done, verified live** | Stage 1 | Hackathon |
| 2a | — entity extraction fields (subject/action/location/time_claim) | **Done, verified live** — fields populated on real observations | Stage 2 | Pilot-grade |
| 2.5 | Evidence-grounded case chat (RAG over the case's own evidence) | **Done, verified live** — real grounded answer, cited real observation IDs, tested over HTTP | Stage 5's embedding pattern | Pilot-grade |
| 3 | Timeline Builder (+ live React timeline UI) | **Done, verified live** | Stage 2 | Hackathon |
| 4 | Discrepancy Detection (3-agent debate: Prosecutor / Defender / Judge, entity-grounded) | **Done, verified live** — replaced single-call adjudication (which caught the planted conflict only 1/4 at low effort, 0/3 at high). Debate caught the planted clock mismatch 3/3 runs with zero false positives on compatible pairs. Full transcript persisted per conflict/link and shown in the Conflict Analysis tab | Stages 3, 11 | Hackathon |
| 4a | — review-status workflow (confirmed/resolved/unresolved) | **Done, verified** — isolated DB round-trip test (set→confirmed→read back confirmed) | Stage 4 | Pilot-grade |
| 4b | — positive evidence linking (supports/related_to) | **Done, verified live** — 6 real links generated with LLM reasoning, served over HTTP | Stage 4 | Pilot-grade |
| 5 | Legal Retrieval (MiniLM embeddings + local ChromaDB) | **Done, verified live** | Stage 0 | Hackathon |
| 6 | Procedural Scene Shell (LLM-generated Three.js, live render) | **Done, verified live** — in the Studio tab. Runtime-compile bug fixed: Babel 8 defaults to the automatic JSX runtime (injects an `import`), now forced to classic runtime + trailing-`;` stripped; verified compiling real LLM output to a React element | Stage 0 | Hackathon |
| 7 | Object Reconstruction | **Done, verified live** — procedural approximation via Muse Wonder (buildgen-style: vision-describe + generate primitive geometry), confirmed real multi-part geometry matching an actual photo. SAM 3D Objects self-hosted (real mesh reconstruction) stays available as an alternate mode once its paused download resumes, not required for "done" | Stage 0; real Meta API key | Hackathon |
| 8 | Segmentation (SAM 3.1) | **Done, verified live** — Meta-hosted via `/v1/responses` (model `sam-3.1`), real box+mask returned on real photos; self-hosted download abandoned, no longer needed. **Backend only** — no API endpoint / UI button yet | Stage 0; real Meta API key | Hackathon |
| 9 | Scenario Comparison | **Done, verified live** (only produces output when Stage 4 finds a conflict — correct dependency behavior) | Stage 4 | Hackathon |
| 9a | — incident reconstruction synthesis | **Done, verified live** — real coherent narrative + specific unresolved gaps generated | Stage 11 | Pilot-grade |
| 10 | Report Export + Audit (hash-chain verified in output) | **Done, verified live** | Stages 3, 4, 9 | Hackathon |
| 11 | Entity Resolution + Relationship Graph | **Done, verified live** — alias-grouping across sources; runs before Stage 4 in both CLI and async-job paths. Graph UI built (dependency-free SVG, `EntityGraph.tsx`): type-grouped layout, click an entity for aliases + relationships, selecting a timeline event rings the entities it mentions (via `entity_mentions`) | Stage 2a | Pilot-grade |
| 12 | Real Auth + Enforced RBAC (JWT, per-endpoint role checks) | **Done, verified live** — unauthenticated 401, wrong-role 403, correct-role 200, tested both directions over HTTP | Stage 0 | Pilot-grade |
| 13 | Secrets management | **Done, verified live** — `.env` deleted, secrets in Windows Credential Manager (`secrets_store.py`), `.env` kept as a portable fallback for anyone cloning the repo elsewhere; tested both paths directly | Stage 0 | Cheap, start now |
| 14 | Input validation & upload sandboxing | **Done, verified live** — real magic-byte checks (fake PDF rejected 400, real PDF accepted, MP4/MOV via `ftyp` at offset 4), size limits enforced; upload filenames stripped of path components (`../../evil.txt` → `evil.txt`, verified); PDF/image parsing now actually runs in the subprocess-isolated worker. Evidence files served only via authenticated `/evidence/{id}/file` (the old public static mount is removed — verified 401 without token) | Stage 1 | Pre-deployment |
| 15 | TLS for localhost | **Done, verified live** — self-signed cert (`scripts/generate_localhost_cert.py`), full test suite + all endpoints confirmed working over `https://127.0.0.1:8010`. Real deployment cert/domain still needed for Stage 20. Note: the current dev run starts uvicorn over plain HTTP — pass `--ssl-certfile/--ssl-keyfile` to serve HTTPS | Stage 0 | Pre-deployment |
| 16 | Rate limiting & abuse protection | **Done, verified live** — tested by hammering `/chat` 16x against a 15/min limit: exactly 15 succeeded, 16th got 429 | Stage 0, 12 | Pre-deployment |
| 17 | Structured logging | **Done, verified live** — JSON-formatted events (provider, latency, errors) confirmed written to `caseweave.jsonl`, 31 real entries captured during testing. Alerting/dashboard still needs real monitoring infra | Stage 0 | Pre-deployment |
| 18 | Data retention & deletion policy | **To do** — needs legal input on retention period first | Stage 0; legal input | Real project |
| 19 | Backup (stopgap) | **Done, verified live** — `backup.py` runs after every `/process`, copies DB + object_store + chroma_store to `Path.home()/"Desktop"` (portable across machines/users, tested on disk). NOT full DR — single location, no offsite/geographic separation, no tested restore procedure yet | Stage 0 | Real project |
| 20 | Scale: MySQL + async job queue | **Done, verified live** — MySQL 8.0 (isolated Docker, port 3307) with zero-call-site-change migration; `/process` now enqueues via Redis/RQ (isolated Docker, port 6381) and returns instantly (0s, confirmed timed) instead of blocking; RQ `SimpleWorker` used since Windows can't fork (`worker.py`); full async round-trip tested live — enqueue → poll `started` → `finished` → real 23-observation result, backup fired automatically inside the job. Remaining for true production scale: multi-worker horizontal scaling (Linux-deployment territory, not buildable/testable on this machine) | Stages 0, 19 | Real project |
| 21 | Dependency vulnerability scanning | **Done, verified** — ran `pip-audit` + `npm audit` for real: 0 CVEs in any package CaseWeave actually imports (fastapi, chromadb, sentence-transformers, pymupdf, PyJWT, bcrypt, slowapi, keyring, cryptography, uvicorn, Pillow, huggingface_hub, all Next.js deps). CI wiring (run-on-every-change) still to do | — (independent) | Cheap, start now |
| 22 | Stronger/paid LLM for court-facing reliability | **To do** — swap Stage 4 + 9a off the free-tier fallback chain | Stages 4, 9a | Cheap, start now |
| 23 | Legal sign-off & compliance certification | **To do** — review, not a build task | Stage 2a's `legal_basis` field | External, book ahead |
| 24 | Independent penetration test | **To do** — must follow Stages 13-17, not precede them | Stages 13-17 | External, book ahead |
| 25 | Real casework validation (shadow pilot) | **To do** — the actual finish line | Stages 0-24 | Finish line |

**Explicitly deferred past this plan, named not forgotten:** task/lead
management, multi-case/multi-org dashboard at scale, multi-agent
orchestration (rejected on purpose), formal multi-case evaluation harness.
Reaching "Done" on Stages 0-12 is real progress — it is not clearance to
handle real case data. That clearance only exists after Stage 25.
