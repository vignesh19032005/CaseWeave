# CaseWeave AI — Complete Project Handoff / Continuity Document

**Purpose of this file:** this is written so a future Claude Code session (or a human) can pick up this project with zero prior context and answer almost anything about what was built, why, what broke, how it was fixed, and what's left — without needing the original chat history. It covers everything discussed across every session of this project, including before any context compaction.

**Last updated:** 2026-10-30 (end of the session that completed the 13-item punch list below)

---

## 1. What CaseWeave Is

CaseWeave AI is an AI-powered investigation/evidence-analysis workspace, originally conceived for a Meta AI hackathon, progressively pushed toward genuine pilot-readiness for a police department (India / Tamil Nadu context). It is explicitly **not** a replacement for FIR systems, chain-of-custody/property-room software, court case-management, or arrest/custody tracking — it is an AI reasoning layer over evidence a department already has: it reads evidence (text, PDFs, photos, audio, video), extracts structured facts, builds a timeline, finds contradictions between sources (with a 3-agent debate, not a single guess), resolves who/what is mentioned where, and produces a reconstruction + report — always with sources cited, always flagging what remains unverified.

**The honest one-line pitch** (validated with the user, use this exact framing when asked "does this work" or "is it the best possible outcome"):

> "This finds contradictions and gaps faster and more consistently than manual review, and cites its sources so you can verify everything — it does not replace investigation, verification, or judgment."

### Explicitly out of scope (decided deliberately, not forgotten)

- FIR registration/Zero FIR/e-FIR — legal act with statutory consequences, a software tool generating something that looks like an FIR is a real legal liability
- Lab integration (DNA/ballistics/fingerprints) — needs physical equipment/partnerships
- Arrest/custody tracking — police procedure with legal time limits, wrong tool for it
- Court-stage features (hearing scheduling, charge framing, witness examination logs, judgment/sentencing, appeals) — that's a court case-management system's job
- Multi-party access/distribution workflow (victim/accused copies) — legal liability if done wrong
- Multi-agent orchestration beyond the one deliberate debate use (the project's own README argues for "modular application, not an elaborate agent network" — the Prosecutor/Defender/Judge debate is a targeted exception for one genuinely ambiguous judgment call, not a general architecture)
- Full photorealistic 3D reconstruction — technically out of reach without real photogrammetry/LIDAR data; the honest ceiling here is procedural approximation, clearly labeled as such everywhere in the UI

---

## 2. Architecture Overview

```
CaseWeave/
├── backend/           FastAPI + Python pipeline
│   ├── api.py                    All HTTP endpoints, auth, CORS
│   ├── auth.py                   JWT auth + RBAC (investigator/reviewer/admin)
│   ├── db.py                     MySQL connection + schema + compatibility wrapper
│   ├── storage.py                Local object store (content-addressed, hash-verified)
│   ├── secrets_store.py          Windows Credential Manager + .env fallback
│   ├── llm_client.py             Meta → Groq → Gemini fallback chain
│   ├── job_queue.py               Async pipeline execution (RQ/Redis)
│   ├── worker.py                 RQ SimpleWorker (Windows can't fork)
│   ├── upload_validation.py      Magic-byte checks, size limits, sandboxed extraction
│   ├── backup.py                 Post-process backup to Desktop
│   ├── run_pipeline.py           CLI entry point (bypasses API, for direct testing)
│   └── pipeline/
│       ├── ingest.py             Stage 0 — case/evidence creation
│       ├── extract.py            Stage 1 — PDF/image/audio/video → text (real extraction)
│       ├── observe.py            Stage 2 — LLM-structured observations
│       ├── timeline.py           Stage 3 — chronological ordering (build + read-only variants)
│       ├── discrepancy.py        Stage 4 — 3-agent debate (Prosecutor/Defender/Judge)
│       ├── legal.py              Stage 5 — legal corpus RAG (MiniLM + ChromaDB)
│       ├── scene.py              Stage 6 — procedural 3D room shell generation
│       ├── reconstruct.py        Stage 7 — procedural object reconstruction (buildgen-style)
│       ├── segment.py            Stage 8 — SAM 3.1 segmentation (backend only, no UI button)
│       ├── scenarios.py          Stage 9 — competing scenario generation
│       ├── report.py             Stage 10 — Markdown report
│       ├── report_pdf.py         Stage 10 (PDF variant) — formatted PDF via reportlab
│       ├── certificate_pdf.py    Draft BSA s.63 electronic-evidence certificate (PDF)
│       ├── entities.py           Stage 11 — entity resolution + relationship graph
│       ├── case_chat.py          Stage 2.5 — evidence-grounded case chat (RAG)
│       └── incident_reconstruction.py  Stage 9a — whole-case narrative synthesis
└── frontend/          Next.js 16 (App Router) + React 19 + Tailwind
    └── app/
        ├── lib/api.ts             Centralized API client, auth, 401 handling
        ├── login/page.tsx         Login screen
        ├── page.tsx               Case Command Center (list/create/delete cases)
        ├── scene/
        │   ├── DynamicScene.tsx   Runtime Babel-compiles LLM-generated JSX → React element
        │   └── page.tsx           Deprecated standalone route (redirects to "/")
        └── case/[caseId]/
            ├── page.tsx           The main 4-tab Incident Reconstruction Studio (huge file)
            └── EntityGraph.tsx    SVG entity/relationship graph component
```

### Data flow (the actual pipeline, in order)

1. Evidence uploaded (text/PDF/image/audio/video) → stored in `object_store/{case_id}/{evidence_id}/`, SHA-256 hash computed and verified
2. **Stage 1** (`extract.py`): every file type converted to text — PDF via PyMuPDF+OCR fallback, images via **vision description + OCR** (see bug fix below — this used to silently skip photos with no text), audio via Groq Whisper, video via audio transcript + sampled frame vision descriptions
3. **Stage 2** (`observe.py`): LLM extracts discrete factual claims per evidence item, each classified `observed | reported | inferred | disputed | unknown`
4. **Stage 3** (`timeline.py`): claims with a resolvable time become timeline events
5. **Stage 11** (`entities.py`): runs **before** Stage 4 now — resolves people/devices/locations across sources, builds relationships; this grounding is fed into the debate
6. **Stage 4** (`discrepancy.py`): candidate pairs of same-topic claims go through a 3-agent debate (Prosecutor argues same-event+conflict, Defender argues compatible/different-events, Judge rules citing which argument was evidence-grounded) → conflicts table (if conflict) or evidence_links table (if supports/related_to)
7. **Stage 9** (`scenarios.py`): alternative explanations generated per conflict
8. **Stage 9a** (`incident_reconstruction.py`): one synthesized narrative across everything, with supported facts + unresolved gaps (now with confidence-scored best-guesses, see below)
9. **Stage 10** (`report.py` + `report_pdf.py`): Markdown and formatted PDF report
10. Backup fires automatically after processing

---

## 3. Current Service State (as of last check this session)

| Service | Status | How to check/restart |
|---|---|---|
| MySQL (Docker, port 3307, container `caseweave-mysql`) | Up | `docker start caseweave-mysql` |
| Redis (Docker, port 6381, container `caseweave-redis`) | Up | `docker start caseweave-redis` |
| FastAPI backend (port 8010) | Up | `cd backend && py -3.11 -m uvicorn api:app --port 8010` |
| RQ worker | Up | `cd backend && py -3.11 worker.py` — **must be running for "Run pipeline" to do anything** |
| Next.js frontend (port 3000) | Up | `cd frontend && npm run dev` |

**IMPORTANT — recurring pattern this session:** the Claude Code *agent session* restarts periodically (context window management), but the actual backend/worker/frontend processes often **survive** those restarts (they're independent OS processes). Always check `curl http://127.0.0.1:8010/health` and `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` before assuming anything is dead — don't blindly restart and lose a mid-run pipeline job.

**Never kill the worker process while a pipeline job is mid-run** — a full run takes 10-20+ minutes (real LLM calls, no shortcuts) and there is no checkpoint/resume; killing it loses all that work and the job shows as "AbandonedJob" in the RQ failed registry.

### Login credentials

- Default admin: `admin` / `changeme123` (bootstrapped on first run if no users table exists — **this gets wiped by** `reset_db()` **calls**, e.g. from `run_pipeline.py`, so if login fails after a CLI run, the admin account was just recreated with these same default credentials)
- JWT token expires after 8 hours — frontend auto-redirects to `/login` on a 401 now (fixed this session, see bug list)

### Known real cases in the database (as of last check)

- `CW-54F2FE` **"Warehouse Incident Demo"** — **THE real demo case.** 14 evidence items: 6 real photos, PDF forensic report, audio + video (added for Stage 1 testing), text statements, access log JSON. Fully processed multiple times, most recently with all 13 fixes active: 177 observations, 28 timeline events, 100 entities, 9 conflicts, 12 evidence links, real PDF report generated (29.8KB). **Use this one for demos.**
- `CW-001` "Warehouse Incident" — same underlying scenario, lighter (CLI-ingested, no photos, evidence not in object_store so API-triggered processing fails with FileNotFoundError — this is expected/known, not a bug, since it was ingested via `run_pipeline.py` directly, not uploaded through the API)
- Other test cases (`CW-8731FE`, `CW-85EDD1`, `CW-71CC58`) were created during testing/debugging and the user was told to delete them via the Command Center's delete button (admin-only, added this session) — **may or may not have been deleted yet, check** `GET /cases`

---

## 4. The Full Stage Status Table (0-25)

This mirrors `PLAN.md`'s "Final Combined Stage List" — check that file directly for the single source of truth table, but here's the summary with what's genuinely verified vs not:

| # | Stage | Status |
|---|---|---|
| 0 | Foundation (FastAPI+Next.js+MySQL+audit+object store) | **Done, verified live** |
| 1 | Media Extraction (PDF/OCR/video/audio/**image vision**) | **Done, verified live** — see bug #5 fix below, this was broken for photos until this session |
| 2 | Observation Engine | **Done, verified live** |
| 2a | Entity extraction fields | **Done, verified live** |
| 2.5 | Evidence-grounded case chat | **Done, verified live** — now with multi-turn conversation history (added this session) |
| 3 | Timeline Builder | **Done, verified live** — now has a proper read-only `get_timeline()` separate from the mutating `build_timeline()` (bug fix, see below) |
| 4 | Discrepancy Detection (3-agent debate) | **Done, verified live, 3/3 reliability confirmed** — see Section 6 for the full story of why this was rewritten |
| 4a | Review-status workflow | **Done, verified live** — now requires a reason on every status change, full history tracked (conflict_reviews table, added this session) |
| 4b | Positive evidence linking | **Done, verified live** |
| 5 | Legal Retrieval | **Done, verified live** |
| 6 | Procedural Scene Shell | **Done, verified live** — prompt rewritten this session to force every named object to actually appear (was generating generic empty rooms) |
| 7 | Object Reconstruction | **Done, verified live** — procedural approximation (buildgen-style); **per-photo UI button removed this session**, folded into the single combined reconstruction instead (user's explicit request — "only 1 reconstruction including all evidence") |
| 8 | Segmentation (SAM 3.1) | **Backend done, verified live** — Meta-hosted, confirmed real box+mask on real photos. **No API endpoint or UI button** — deliberately not wired up, lower priority |
| 9 | Scenario Comparison | **Done, verified live** |
| 9a | Incident reconstruction synthesis | **Done, verified live** — now includes confidence-scored unresolved gaps (added this session) |
| 10 | Report Export + Audit | **Done, verified live** — now has a real formatted PDF alongside Markdown (added this session) |
| 11 | Entity Resolution + Relationship Graph | **Done, verified live** — real SVG graph UI built this session (`EntityGraph.tsx`), alias-dedup bug fixed |
| 12 | Real Auth + RBAC | **Done, verified live** |
| 13 | Secrets management | **Done, verified live** |
| 14 | Input validation & upload sandboxing | **Done, verified live** — filename path-traversal sanitization added this session (`../../evil.txt` → `evil.txt`) |
| 15 | TLS for localhost | **Built, not currently running** — the dev servers run plain HTTP; the cert script exists and works, just not invoked in the current startup commands |
| 16 | Rate limiting | **Done, verified live** |
| 17 | Structured logging | **Done, verified live** |
| 18 | Data retention & deletion policy | **To do** — needs legal input first |
| 19 | Backup | **Done, verified live** |
| 20 | MySQL + async job queue | **Done, verified live** |
| 21 | Dependency vulnerability scanning | **Done, verified** (pip-audit + npm audit, 0 CVEs found) |
| 22 | Stronger/paid LLM | **To do** |
| 23 | Legal sign-off | **To do, on hold** (user explicitly said "hold 23 for now") |
| 24 | Penetration test | **To do**, external |
| 25 | Real casework validation (shadow pilot) | **To do** — the actual finish line |

---

## 5. The 13-Item Punch List (this session's main work) — ALL DONE

The user gave detailed low-level feedback on the live UI and asked for all 13 items, one by one, with testing after each. **All 13 are complete and individually verified.**

1. **"Run pipeline" parse error** — FIXED. Root cause: `python-multipart` throws "There was an error parsing the body" on a genuinely empty multipart form body (zero fields) — exactly what the browser sent when no legal query was entered. Fix: converted `/cases/{id}/process` from a `Form(...)` multipart endpoint to a plain JSON body endpoint (`ProcessRequest` Pydantic model), matching every other endpoint in the file. Verified via curl replicating the exact empty-multipart-body browser behavior before and after.
2. **Evidence list scrollbar overlapping text** — FIXED. Added `pr-2` padding-right to all 5 scrollable list containers in the case page so the native browser scrollbar doesn't sit on top of the text.
3. **Timeline click loses context (page doesn't scroll to show the result)** — FIXED. Added a `ref` + `useEffect` on the "Selected event" panel that calls `scrollIntoView({behavior: "smooth", block: "start"})` whenever `selectedEventId` changes, so clicking a timeline event always brings its detail panel into view regardless of current scroll position.
4. **Entity "also referred to as: X" showing X = the canonical name itself** — FIXED in `EntityGraph.tsx`. Added filtering so only aliases that differ (case-insensitive) from the canonical name are shown; if none remain, the line doesn't render at all. Unit-tested the filter logic directly.
5. **Only ONE combined reconstruction (not per-photo)** — FIXED, and this surfaced a **real underlying bug**: `extract.py`'s image handling only ran OCR (text-in-image detection) — a photo with no legible text (the overwhelming majority of evidence photos, e.g. "toppled chair", "torn-open box") was **silently skipped entirely** from the observation pipeline. Fixed by adding a real vision-description pass (`PHOTO_DESCRIPTION_PROMPT`) that runs on every photo regardless of OCR result, combined with OCR text when present. Verified live: a real evidence photo of a toppled chair + scattered papers + box + laptop now produces a detailed, accurate description feeding into observations. The per-photo "Reconstruct" button and its API endpoint were removed entirely (dead code cleaned up); the single "Generate reconstruction" (narrative) and "Generate scene" (3D) in the Studio tab are now fed by this richer data.
6. **Unresolved gaps need a best-guess + confidence score, not just a bare question** — FIXED. Rewrote `incident_reconstruction.py`'s prompt to require `{question, best_guess, confidence (low/medium/high/none), basis}` per gap instead of a bare string, with graceful degradation if the model ignores the schema. Rendered in both the Studio tab UI (color-coded by confidence) and the PDF/Markdown reports, always clearly labeled "unverified, not a finding."
7. **Conflict "verification question" should be a clearly-labeled recommended next step** — FIXED. Relabeled in the UI from "Verification question" to "Recommended next step" with an explanatory note: "This does not resolve the conflict — it tells you what to go check." Also explained to the user *why* a conflict can legitimately stay a conflict after the debate: the debate decides *whether* a real discrepancy exists, not *which side is true* — that needs a human checking real evidence the system doesn't have.
8. **Require a reason when changing conflict status (confirmed/resolved/unresolved), with full history** — FIXED. New `conflict_reviews` table (review_id, case_id, conflict_id, status, reason, actor_username, actor_role, timestamp). `update_review_status()` now requires a non-empty reason and inserts a history row on every change. New endpoint `GET /cases/{id}/conflicts/{id}/reviews`. Frontend uses a `prompt()` to require the reason before submitting, and a `ReviewHistory` component shows the full audit trail per conflict. Verified via curl: empty reason → 400, valid reason → 200 + history entry recorded correctly.
9. **Formatted, downloadable PDF report (not raw Markdown)** — FIXED. New `pipeline/report_pdf.py` using `reportlab` (already installed) — real typeset document with colored section headers, bordered tables for evidence/timeline, highlighted conflict boxes, not an HTML→PDF conversion (built directly from the same source data as the Markdown report so they can't drift apart in content). **Found and fixed a real XSS-adjacent bug during testing**: initially all data was double-escaped or not escaped at all depending on the code path, breaking the reportlab Paragraph parser on any evidence text containing `&`, `<`, or `>`. Fixed with a clean `esc()` helper for data values vs. trusted template markup, and explicitly injection-tested with fake conflict data containing `<script>`, `&`, and `<b>` before trusting it. New endpoint `GET /cases/{id}/report/pdf`, frontend download button added, included in the delete-case cleanup cascade.
10. **Chain-of-custody / access log view** — FIXED. New "Chain of custody" section in Evidence Explorer: every evidence item is clickable to expand its full audit history (every action taken against it, by whom, when) — built entirely from the existing hash-chained `audit_events` table, no new backend tracking needed, just a UI view. Verified against real data (13 real historical events found for one evidence item across multiple past pipeline runs).
11. **Formal per-evidence chain-of-custody summary** — Covered by item 10's expandable panel (shows SHA-256 hash, evidence ID, and full event history per item) — judged sufficient, no separate feature needed.
12. **Draft electronic-evidence certificate (BSA s.63 style)** — FIXED. New `pipeline/certificate_pdf.py` — a one-page PDF per evidence item with a prominent "DRAFT — NOT A LEGAL CERTIFICATE — FOR REVIEW AND FORMAL EXECUTION BY COUNSEL ONLY" banner, record identification (hash, filename, type), production/custody narrative (built from the audit log), extraction method, and a blank statement template for counsel to complete and sign. New endpoint `GET /cases/{id}/evidence/{id}/certificate`, download button added next to each evidence item's chain-of-custody panel. Hit the same style-object-vs-style-name bug as item 9 during testing (`Paragraph(text, "StyleName")` instead of `Paragraph(text, styles["StyleName"])`) — fixed with the same `_p()` helper pattern, verified via real HTTP round-trip (200, valid 1-page PDF, 3758 bytes).
13. **Structured witness-statement intake form** — FIXED. New `WitnessStatementForm` component in Evidence Explorer: guided fields (witness name, role, date, time, location, contact, statement text) that formats into a labeled text document and uploads through the exact same evidence pipeline as any other file (built via the browser's `DataTransfer`/`File` APIs to construct a real `FileList`, no new backend endpoint needed). Formatting logic unit-tested directly.

### Bonus fixes found and done along the way (not originally numbered, but real)

- **Delete-case endpoint** (`DELETE /cases/{id}`, admin-only) — added because the user accidentally created a stray case and there was no way to remove it. Cascades across all case-scoped tables, object_store files, and the Chroma chat index. UI delete button added to Command Center with a confirm dialog. *(This specific destructive action was correctly blocked by the safety classifier when attempted via raw curl — the user was directed to use the UI button instead, which requires an explicit confirm click.)*
- **Frontend auto-redirect on 401** — centralized in `api.ts`'s `request()` so an expired/invalid token redirects to `/login` from anywhere instead of showing a dead error banner forever (except on the login endpoint itself, where a 401 means wrong password, not an expired session).
- **Next.js 16** `useParams()` **in a Client Component blocking prerendering** — fixed by wrapping the case page in `<Suspense>`.
- **3D scene runtime compile crash ("Cannot use import statement outside a module")** — two-layer root cause found and fixed: (a) Babel 8's React preset defaults to the "automatic" JSX runtime which injects an `import` statement that `new Function()` can't evaluate — forced classic runtime; (b) Babel's output is an expression *statement* with a trailing `;` which breaks `return (...)`  — stripped it. Also stripped stray `import`/`export` lines the LLM occasionally emits despite being told not to, at both the backend generation point and defensively in the frontend compile step. Verified by compiling real LLM-generated scene JSX (199 elements) end-to-end through the actual fixed code path.
- **Pipeline idempotency** — re-running `/process` on a case used to pile up duplicate observations/timeline events/conflicts on top of old ones (no DELETE-before-INSERT). Fixed across `observe.py`, `timeline.py`, `discrepancy.py` to clear the case's prior rows at the start of each run.
- **Audit hash-chain forking under concurrent writers** — traced a real `audit chain: FAILED` to two processes (API + worker) racing to read "the latest hash" and both chaining off the same stale value. Fixed with a MySQL `GET_LOCK`-based serialization in `append_audit_event()`.
- **MP4/MOV magic-byte validation false rejection** — the `ftyp` box signature appears at byte offset 4, not 0 (the first 4 bytes are a variable box-size field) — fixed `upload_validation.py` to check at the right offset.
- **LLM call retry hardening** — `_post_json()` in `llm_client.py` originally only retried on HTTP 429/503; a raw socket `TimeoutError` or `http.client.RemoteDisconnected` (observed in practice right after a Docker/network restart) would fail the whole pipeline immediately. Broadened the retry to cover `TimeoutError`, `URLError`, `ConnectionError`, `OSError`.
- **Job timeout too short for real multi-photo cases** — RQ's `job_timeout` was 600s, measured real runtime for an 11-14 item case with photos is 10-20+ minutes. Raised to 1800s.

---

## 6. Deep-Dive: Why the Discrepancy Detection (Stage 4) Was Rewritten

This is one of the most-discussed technical threads across the whole project and worth having the full reasoning available.

**The original approach**: a single LLM call given two claims, asked to judge whether they conflict. **Measured directly on this project's own planted test conflict**: caught it only 1-in-4 times at low reasoning effort, and 0-in-3 times at high reasoning effort — raising reasoning effort counterintuitively made the model *more* willing to explain the conflict away, not less. The task is genuinely ambiguous to a single pass: "a device timestamp and a human estimate 6 minutes apart" is a defensible "different events" read in isolation, and a single holistic judgment call doesn't reliably apply a consistent rule.

**The fix**: a 3-agent debate, implemented in `discrepancy.py`:

1. **Prosecutor** — builds the strongest case that two claims describe the same event with a genuine conflict. Not neutral, explicitly advocacy-grounded, same as a real investigator stress-testing a theory.
2. **Defender** — builds the strongest case that the claims are compatible or describe different events. Explicitly told: "it's possible they're different" is not enough — needs a concrete, evidence-based reason, or state honestly that none exists.
3. **Judge** — reads both arguments plus the shared evidence and any entity-resolution context, rules based on which argument is more evidence-grounded (not by splitting the difference or being lenient). Weak/non-evidence-based Defender arguments lose.

All three agents are grounded by a shared **DECISION_RUBRIC** (same text for all three, to prevent each agent silently substituting its own standard):

- Same event type + same resolved entity/location + no third evidence of separate occurrences → treat as ONE event, any difference is a genuine conflict, not grounds to call them unrelated
- A timestamp gap alone (even 15-30 min, device-vs-human) is NOT grounds for "different events" by default
- Only classify as related_to/unrelated with a *concrete, evidence-based* reason

**Entity-resolution grounding**: Stage 11 (entity resolution) was reordered to run *before* Stage 4 specifically so its output ("these two claims already resolved to the same canonical entity") can be handed to all three agents as an established fact, removing one whole axis of legitimate ambiguity.

**Result, verified**: 3 full pipeline runs, zero false positives on compatible claims, zero misses on the real planted conflict, consistent reasoning every time. Full transcripts (every agent's argument + the Judge's reasoning) are persisted per conflict in the database (`transcript` column, JSON) and shown in the Conflict Analysis tab's UI — not a black box.

**Live demo of this**: the user explicitly asked to see the debate happen live (not just the final verdict), which was built as `live=True` per-agent console printing in `_debate_adjudicate()` — prints "[Prosecutor is arguing...]" → full argument text → "[Defender is arguing...]" → etc. the instant each LLM call returns. This is *not* token-level streaming (that would need a bigger SSE-based rewrite of `llm_client.py`, explicitly flagged as a bigger lift and never built) — it's per-call live printing, which was sufficient for what the user wanted to see.

---

## 7. Deep-Dive: Meta API Integration (how it actually works)

This took significant debugging across the session and is worth documenting precisely.

- **Real endpoint**: `https://api.meta.ai/v1/responses` — **not** `api.llama.com/v1/chat/completions`, which was an earlier wrong guess based on general knowledge that cost significant debugging time (persistent 401s) before the user provided official docs/curl examples.
- **Request shape**: OpenAI-"Responses-API"-style, not OpenAI-"Chat Completions"-style. Uses an `input` field (string, or an array of content blocks for vision), **not** a `messages` array.
  ```python
  payload = {
      "model": "muse-wonder-1.0",
      "input": f"{system}\n\n{prompt}",   # text case
      "reasoning": {"effort": "high"},
  }
  # vision case: input is an array:
  "input": [{"role": "user", "content": [
      {"type": "input_text", "text": "..."},
      {"type": "input_image", "image_url": f"data:{mime};base64,{b64}"},
  ]}]
  ```
- **Response shape**: parse from `output[].content[].output_text` where `output[].type == "message"`.
- **Models actually used**: `muse-wonder-1.0` (text + vision reasoning), `sam-3.1` (segmentation, same endpoint, different model value — this is how Stage 8 got unblocked: it turned out to be hosted at the same endpoint already in use, no separate self-hosted SAM 3 download needed after all).
- **Segmentation output format**: raw text containing `<box;x1=...;y1=...;x2=...;y2=...><mask;...>` tags — parsed with regex, not JSON.
- **Reasoning effort**: a genuine parameter (`{"effort": "low"|"high"}`), affects token cost; raising it did **not** improve Stage 4 reliability (see Section 6) — that's a finding specific to this use case, not a general claim about reasoning effort.

---

## 8. Fallback Chain & Known Provider Quirks

`llm_client.py`'s `chat()`/`chat_json()`/`chat_vision()` try Meta → Groq → Gemini in order, logging a warning if a non-Meta provider answers (hackathon rule: disclose non-Meta fallback use).

- **Groq**: blocked by Cloudflare with default urllib User-Agent — fixed with an explicit `"User-Agent": "Mozilla/5.0 (CaseWeave/1.0)"` header on all calls. Model `llama-3.3-70b-versatile` returned 404 on this account (not available) — switched to `openai/gpt-oss-20b`, explicitly disclosed as non-Meta. That model has hidden reasoning that burns tokens before emitting the actual answer — small `max_tokens` budgets left nothing for the real response; fixed with `reasoning_effort: "low"` + raised `max_completion_tokens`. No vision-capable model available on this account's Groq key (checked via `/v1/models`).
- **Gemini**: `gemini-2.0-flash` deprecated, switched to `gemini-3.8-flash`. Intermittent 503 "high demand" — added to the retry-with-backoff condition.
- **Retry logic**: exponential backoff (2s/4s/8s) on HTTP 429/503, and (added this session) on raw connection-level failures (TimeoutError/URLError/ConnectionError/OSError) too.

---

## 9. Frontend Structure Detail (`app/case/[caseId]/page.tsx`)

This is a large single file (~1300+ lines) organized as:

- `CaseStudioPage` (default export) — wraps everything in `<Suspense>` for Next.js 16's `useParams()` requirement
- `CaseStudio` — the real component, owns all state, data loading (`loadAll`/`refreshDerived`), and the 4-tab layout
- Tab components, each a separate function: `EvidenceExplorer`, `StudioTab`, `ConflictsTab`, `ReportTab`
- Supporting components: `EvidenceImage` (authenticated image loading via blob URL, since `<img src>` can't send Authorization headers), `WitnessStatementForm`, `ReviewHistory`, `Stat`
- `EntityGraph.tsx` is a separate file — dependency-free SVG graph, no library, deterministic circular layout grouped by entity type, click-to-inspect

**Key design pattern used throughout**: authenticated file downloads/images use `fetch()` + `URL.createObjectURL(blob)` + a programmatically-clicked `<a download>`, never a raw `<img src>` or `<a href>` pointing at the API, because those can't carry the Bearer token.

**State ownership**: `CaseStudio` owns everything and passes down via props (not context) — evidence, timeline, conflicts, evidenceLinks, entities, relationships, mentions, auditStatus, auditEvents, narrative, chatHistory, scene state, etc.

---

## 10. What's Explicitly NOT Done / Known Gaps

- **Stage 8 (segmentation) has no UI** — backend works, confirmed live, but there's no API endpoint or button exposed. Low priority per user, not touched.
- **Stage 15 (TLS)** — the cert-generation script exists and was verified working in an earlier session, but the current dev startup commands (`uvicorn api:app --port 8010`, `npm run dev`) run plain HTTP. To enable: `uvicorn api:app --ssl-certfile=... --ssl-keyfile=...` using the output of `scripts/generate_localhost_cert.py`.
- **Stages 18, 22, 23, 24, 25** — need people outside the code (lawyers, a pen-test firm, a police unit for the shadow pilot). Code alone can't finish them; explicitly discussed with the user as the honest ceiling of what this project can be "done."
- **No automated test suite run this session** — `backend/tests/test_pipeline.py` exists from earlier sessions (22 checks) but wasn't re-run against this session's changes; worth running before considering the punch-list work fully "regression-safe."
- **CORS is locked to** `localhost:3000`**/**`127.0.0.1:3000` — fine for local dev, would need updating for any real deployment.
- **No automated CI** — dependency scanning (`pip-audit`/`npm audit`) was run manually once, not wired to run on every change.

---

## 11. How To Resume Work (exact commands)

```bash
# 1. Start Docker containers (if not already up)
docker start caseweave-mysql caseweave-redis

# 2. Start backend (from backend/ directory)
cd "C:\Users\VIGNESH\Downloads\CaseWeave\backend"
py -3.11 -m uvicorn api:app --port 8010
# (or with PYTHONUTF8=1 env var set first, for clean console output on Windows)

# 3. Start the worker — REQUIRED for "Run pipeline" to do anything
cd "C:\Users\VIGNESH\Downloads\CaseWeave\backend"
py -3.11 worker.py

# 4. Start frontend
cd "C:\Users\VIGNESH\Downloads\CaseWeave\frontend"
npm run dev

# 5. Open http://localhost:3000, log in as admin / changeme123
```

**To verify everything is actually working, not just "running":**

```bash
curl http://127.0.0.1:8010/health
# Then log in, create/open a case, upload evidence, click "Run pipeline",
# and watch the worker's stdout for "llm call succeeded" lines — that's
# proof real LLM calls are happening, not a mock.
```

**Before touching destructive operations** (deleting a case, `reset_db()`, force-restarting a mid-job worker): check `GET /cases` and the worker log first. The delete-case button requires an explicit confirm click in the browser — if asked to delete via raw API/curl, expect (and respect) the safety classifier blocking it; direct the user to the UI button instead.

---

## 12. Things The User Has Explicitly Asked Not To Do / Preferences Observed

- Caveman-mode terse responses are the session default once activated (`/caveman`) — drop articles/filler/hedging, but never on code/commits/security explanations.
- Stage 23 (legal sign-off) is on explicit hold — don't start it unprompted.
- The user wants to personally click the delete-case button rather than have it done via curl on their behalf — respect this boundary even if it seems like a shortcut.
- The user values live, verified testing over claims — every fix in this session was verified against the real running stack (curl round-trips, real DB queries, real PDF byte-content checks, actual LLM calls), not just "should work" reasoning. Keep this standard.
- When something breaks, the user wants root-cause analysis, not a workaround — multiple bugs this session (multipart parsing, Babel JSX runtime, audit hash-chain forking, MP4 magic bytes) were traced to their actual cause rather than patched around.

---

## 13. Quick Reference — File Locations for Common Questions

- "What does stage X actually do" → `backend/pipeline/<name>.py`, each has a docstring explaining the stage number and real implementation details
- "What's the full stage status" → `backend/PLAN.md`'s "Final Combined Stage List" table (single source of truth, more detail than Section 4 above)
- "What API endpoints exist" → `backend/api.py`, search for `@app.`
- "What does the UI look like / what can I click" → `frontend/app/case/[caseId]/page.tsx`
- "Why did the debate system get built this way" → Section 6 above, or `backend/pipeline/discrepancy.py`'s module docstring (very detailed, written for exactly this purpose)
- "What's the Meta API's real shape" → Section 7 above, or `backend/llm_client.py`
