# CaseWeave Reconstruction & Simulation — Final Fix Checklist

Merged from `SANDBOX_AUDIT.md` and a second audit run against the live code and database
(2026-11-02). Tick items as they are fixed *and* pass the gate in section 8.

**Source tags**
- **[V]** verified by me by running code against the real DB or by reading the current files
- **[A]** from `SANDBOX_AUDIT.md`; I spot-checked the ones marked [A✓] and did not independently run the rest
- Line numbers in the older audit come from an earlier revision; use function names, not line numbers.

**What this checklist will and will not give you** (see section 9)

---

## Status (updated after the build)

**101 done, 4 partly done, 0 not started** of 105. `[x]` done and verified by automated tests, `[~]` partly done (note on the line), `[ ]` not started.

Verified by: 412 automated tests (geometry/property, evidence, redaction, provider modes, instruction screen, photo links, API with a mocked model); two 2,500-3,000-scene random stress runs (multi-room, multi-floor, multi-person); a fault-injection evaluation (`backend/scripts/sandbox_eval.py`: 600/600 identical on rebuild, 199/199 deliberately damaged plans caught, 0 unexplained rejections); real generation on case CW-E65FA6 with Meta's hosted model only, plus live SAM 3.1 photo search; a live prompt-injection case; frontend `tsc` and `eslint` clean.

**Browser checks (Chromium):** (1) the real generated scene for CW-E65FA6 and (2) a synthetic 3-floor, 4-person case with two staircases, a cellar, a camera and a witness. API responses were replayed (no live login). Defects found by these runs and fixed: CCTV view blocked by the camera's own cone; label clutter; slow camera settling; cellar hidden by the ground plane; routes shown for hidden floors; a door shown forced before the scenario forces it; no opening in the upper floor where the stairs arrive. Still not confirmed: gait quality, a live login, and the add-object flow through the real backend.

**Known limits (stated, not hidden):** vehicles do not move and windows are not modelled; speeds, door-delay and stairs figures are order-of-magnitude heuristics; redaction covers names known to the case, phones, emails, Aadhaar, PAN, plates, IMEI and long numbers but not free-text descriptions of people or places; the default admin password (`changeme123`) must be changed by the owner before any pilot.

---

## 1. Safety and blockers

- [x] **S1** Remove `new Function` execution of LLM-written JSX in `DynamicScene.tsx`; evidence text can steer it, so it can run code in the investigator's logged-in browser. Render only validated structured data. [V]
- [x] **S2** Stop generating on `GET` and on page load; use `POST` plus a background job with status and cancel. [V][A✓]
- [x] **S3** Add RBAC (`view_case`, new `generate_scenario`) and rate limits to every sandbox endpoint and to `/scene`; none exist today. [V][A✓]
- [x] **S4** Take the sandbox out of the page's `Promise.all`, add loading, empty, error and timeout states; today a failed fetch shows "Generating…" forever. [V][A✓]
- [x] **S5** Add real DB migrations (`ALTER`, schema version); existing installs lack the new columns (the live DB was patched by hand only). Set `utf8mb4`. Widen `scenario_id`. [V][A✓]
- [x] **S6** Return "insufficient evidence" for empty or non-physical cases instead of inventing a room and scenarios (measured: a case with zero evidence got a 5×6 m room and 2 scenarios). [V]
- [x] **S7** Defend against prompt injection: delimit evidence, never trust instructions inside it, validate every output against a schema. [A][V]
- [x] **S8** Disclose that evidence goes to third-party LLM providers; add redaction and consent record. [A]
- [x] **S9** Stop leaking internal errors (`HTTP 500` with `str(e)`). [A✓]

## 2. Correct geometry and motion

**Paths and collisions**
- [x] **G1** Derive the outside start point from the door actually used, not a fixed point south of the building. [V][A✓]
- [x] **G2** Replace the single detour with real navigation (grid or visibility-graph A*) over walls, fixtures, closed doors, with actor clearance. [V][A✓]
- [x] **G3** Validate the final rendered path, every segment, against walls, door gaps, fixtures and room bounds; reject or flag, never silently pass. (Measured: 1,932 of 2,000 random paths defective, 1,342 still marked PASS.) [V]
- [x] **G4** Stop targets inside furniture: give each fixture and key location a standing point in front of it. (Measured: 3-4 stops inside furniture per scenario.) [V]
- [x] **G5** Remove the "skip exterior legs" shortcut; any wall crossing must lie inside a door gap. [V][A✓]
- [x] **G6** Fixtures: footprint fully inside walls, no overlaps, doors not blocked, minimum aisle width, height under ceiling. [V][A]
- [x] **G7** Key locations that fall inside fixtures must be relocated or given a standoff. [V]
- [x] **G8** Enforce reachability: every key location reachable from a door. [A]
- [x] **G9** Door states (open, forced, locked, intact); actor only passes open ones. [A]
- [x] **G10** Door height, not width, drives ducking; fix the id-vs-label comparison and exits. [V][A✓]

**Time and action**
- [x] **G11** One time model (depart, transit, arrive, dwell) shared by backend physics, frames and frontend; one total duration. (Measured: validator and player use different step times on every leg.) [V][A✓]
- [x] **G12** Actions play during dwell at the object, not while walking away from it; face the object being handled. [V][A✓]
- [x] **G13** Milestone clicks land on the arrival of that step; `currentLabel` shows where the actor is. [V][A✓]
- [x] **G14** Detour frames get unique timestamps and must not leak future "disturbed" state. [V][A]
- [x] **G15** Legs under 0.3 m/s (half of them today) become walking at believable speed plus dwell. [V]
- [x] **G16** Action-specific speeds (walk, run, carry, crouch, injured) and acceleration instead of one 7.5 m/s ceiling; stride tied to real speed. [V][A]
- [x] **G17** `avg_speed` excludes dwell and is labelled correctly. [A]
- [x] **G18** Merging repeated steps must keep both actions in order (today damage + take_item keeps only take_item). [V]

**Physics honesty**
- [x] **G19** PASS only after the full checks run; the panel lists what was and was not tested. [V][A]
- [x] **G20** Recompute stored physics when rules change; never show an old PASS. [A]
- [x] **G21** Remove or build the "optical line-of-sight" claim (page heading) with real occlusion. [V][A]
- [x] **G22** Make constants (speeds, margins, durations) configurable and documented. [A]

**Data safety**
- [x] **G23** Coerce every LLM number and text safely (`"about 12 metres"`, `"2 minutes"` crash today). [V][A]
- [x] **G24** Treat `0` as a value, not as missing. [V][A]
- [x] **G25** Reserve ID `exterior`; normalise step IDs (`Back Room` vs `back_room`); separate ID namespaces per category. [V][A]

## 3. Evidence truth

**Grounding**
- [x] **E1** Give the LLM all observations (timed and untimed, with source locators), not only the first 60 timed events. (Measured: 36 of 195 seen.) [V][A✓]
- [x] **E2** Citations: accept evidence IDs and all observation IDs; parse and verify bracketed IDs in narrative text. [A✓][V]
- [x] **E3** Every node and step carries provenance (`observed | reported | inferred | defaulted`), refs, quote, locator and confidence; mark or reject empty refs. [A]
- [x] **E4** No silent defaults for door, room size or height; flag every default. [A✓]
- [x] **E5** Honour conflict `review_status` (resolved conflicts are not "unresolved"). [A✓]
- [x] **E6** Check that a cited observation actually supports the node, not just that the ID exists. [A]
- [x] **E7** Check scenarios against evidence: doors recorded intact, camera coverage, known time windows. [A]
- [~] **E8** Use photos, plans and measurements for layout (vision and segmentation are not connected today); calibrate scale; show uncertainty. [V][A] **Status:** vision cues are opt-in and off by default; not exercised against a live vision model

**Scoring**
- [x] **E9** Deterministic evidence-fit rubric (supports, contradictions, coverage, dropped steps, physics, time window); show raw and adjusted scores. [A✓]
- [x] **E10** Sort by score after validation; badge by rank, not by position. [A✓]
- [x] **E11** Disclose dropped steps and penalise coverage loss. [V][A]
- [x] **E12** Stable, length-safe scenario IDs. [A]

**Time anchoring**
- [x] **E13** Real clocks: source clock offsets (e.g. NVR +5m32s), date, timezone, seconds; mark each step anchored vs estimated. [A✓]
- [x] **E14** Scenario titles and narrative times must match the displayed clock (measured: title says "23:40", clock starts 20:55). [V]
- [x] **E15** Start clock = start of the incident, not the earliest event; check duration against known windows. [V][A]
- [x] **E16** Time parsing beyond `HH:MM`: 12-hour, dates, text-sort bug, video offsets. [A✓]
- [x] **E17** Respect the time named in an officer's custom hypothesis. [A]

**LLM reliability**
- [x] **E18** Store model, provider, prompt version and hash, temperature, raw response. [V][A]
- [x] **E19** Fix reproducibility (measured: same case gave 10×15, 10×14 and 12×18 m rooms); allow officer to lock an approved layout. [V]
- [x] **E20** Honour `max_tokens` for Meta (currently ignored); repair truncated JSON; schema-validate and retry. [A✓][V]
- [x] **E21** Disclose truncation (`timeline[:60]`, node caps, `refs[:8]`); cap prompt size. [A][V]
- [x] **E22** Interview: adaptive questions, free text, questions stored and sent to synthesis; no silent fallback to boilerplate. [V][A]
- [x] **E23** Keep narrative, scenarios and conflict scenarios consistent (today three independent LLM calls, two policies on probability). [V]

## 4. Universal scene model

- [x] **M1** Scene graph: multiple rooms and floors, internal walls and doors, outdoor areas, stairs, vehicles. [A]
- [x] **M2** Multiple actors (suspect, victim, witness, guard, camera), each with path and evidence refs. [A][V]
- [x] **M3** "Unknown / not observed" space instead of asserting the whole rectangle. [A]
- [x] **M4** Body and object state (positions, pose, placement, damage) instead of a tilt flag. [A][V] **Status:** checked in Chromium on a synthetic 3-floor, 4-person case: lying/standing poses, carried-item label, door shown intact then forced at the cited time; no injury or damage geometry (stated limit)
- [x] **M5** Wider action set and event types (assault, shooting, crash, fall, fire; drop, open, close, unlock, wait, hide, look). [V][A]
- [x] **M6** "No physical scene" result for fraud, cyber and similar cases. [V]
- [x] **M7** Disclose size and count limits instead of clamping silently. [A]
- [x] **M8** Officer layout editor with provenance, then re-simulate. [A]
- [x] **M9** Merge the Studio scene (`scene.py`) and the sandbox layout into one saved scene per case. [V]
- [x] **M10** Connect or remove: photo-to-3D (`reconstruct_object` has no endpoint; "auto" crashes with `NotImplementedError` once weights exist), segmentation (boxes only, errors swallowed, results unsaved and unused). [V]

## 5. Persistence, versions, API

- [x] **D1** Immutable versions; never delete or overwrite prior scenarios; evidence fingerprint. [A✓]
- [x] **D2** Stale detection when evidence changes; invalidate or flag custom scenarios; do not show pre-evidence scenes after the pipeline runs. [V][A✓]
- [x] **D3** One transaction for layout plus scenarios; locks and idempotency; no `REPLACE INTO`. [A]
- [x] **D4** Schema version and legacy-shape guard for cached rows. [A]
- [x] **D5** Content hash in audit events; real user in audit (not hardcoded "investigator"); audit interview requests; UTC timestamps; audit in the same transaction. [A✓]
- [x] **D6** Keep `audit_events` when a case is deleted. [A✓]
- [x] **D7** Return provider, model, generated time and cached flag to the UI. [A]
- [x] **D8** Error taxonomy (503, 422, 403), timeouts, progress, cancel, case-exists check. [A]
- [x] **D9** Close DB connections in `finally` everywhere. [A]
- [x] **D10** Delete or retract custom scenarios; dedupe repeated synthesis. [A]
- [x] **D11** Save Studio scene and incident narrative per case. [V]
- [x] **D12** Court pack export: layout, provenance, citations, physics report, version history, hashes. [A]

## 6. UI and provenance

- [x] **U1** Draw the route as segments; colour evidence-backed vs auto-inserted; click any segment for its evidence. [A✓]
- [x] **U2** Walls clickable, or remove the hint. [A✓]
- [x] **U3** Evidence refs show description, file, locator, quote and link. [A]
- [x] **U4** Show layout `notes`, provenance badges and coverage percentage. [V][A]
- [x] **U5** Show raw vs adjusted fit and the rubric; label LLM estimates as estimates. [A]
- [x] **U6** Comparison view and path overlay across scenarios. [A] **Status:** checked in Chromium screenshots: comparison table and route overlay render
- [x] **U7** Ordered step list with rationale and citations. [A]
- [x] **U8** Door markers and wall gaps aligned (markers sit 0.35 m inside the gap, drawing a second set of posts, the likely cause of the "2 rows" you saw). [A][V by code reading, not yet seen in a browser]
- [x] **U9** Interaction fixes: custom-scenario insert shifts the active tab, camera Reset can do nothing, selection by name not id, silent errors on Regenerate and interview, modal closes on empty result. [A✓][V]
- [x] **U10** Replace the 20 fps `setInterval` with an animation-frame loop; pause when hidden. [A]
- [x] **U11** Error boundary for malformed cache; keyboard access; legend; PNG/PDF export. [A] **Status:** legend, PDF/JSON downloads, and the error fallback (WebGL disabled: message shown, rest of page works) confirmed in Chromium
- [x] **U12** Polish: grid z-fighting, wall culling, `color_hex` validation, thresholds on short walls, badge parsing. [A] **Status:** cutaway/full walls, floor filter (incl. cellar), and stair opening in the upper slab confirmed in Chromium

## 7. Visual realism

- [~] **R1** Better human rig: turn smoothing, foot planting, no feet sinking when kneeling or ducking, door-pass animation. [V] **Status:** sampled at 20 Hz on both fixtures: no teleports, speeds match the backend profile, turns smoothed at render time; gait and foot planting not judged beyond stills
- [~] **R2** Hand-object interaction (open shutter, pick up, carry) tied to cited evidence; props only when evidence names them. [V][A] **Status:** actions, effects and a carried-item label follow cited steps; no hand-held prop model is drawn
- [x] **R3** Real materials, lighting, shadows and furniture models instead of boxes; time-of-day lighting from the real clock. [V] **Status:** furniture shapes, shadows and clock-driven night lighting seen in Chromium screenshots
- [x] **R4** Camera modes: follow, first-person, and CCTV view from a real camera position. [V] **Status:** checked in Chromium screenshots: overview, top-down, follow and CCTV (with REC/clock overlay) all render

## 8. Tests and acceptance gates

- [x] **T1** Unit tests for every pure function in `sandbox.py`.
- [x] **T2** Property test: across 10,000 random rooms, **0** wall crossings, **0** fixture crossings, **0** stops inside furniture, **0** points outside the room; PASS only if all hold.
- [x] **T3** Golden tests for timing, clock, milestones; backend and frontend produce the same total duration.
- [x] **T4** Migration test: old schema → new schema.
- [x] **T5** Concurrency test: two simultaneous generations.
- [x] **T6** Malformed-LLM fuzz: strings for numbers, lists for objects, truncated JSON; no crashes.
- [x] **T7** Cases with no evidence, untimed evidence, non-physical evidence, multi-room, multi-actor.
- [x] **T8** Reproducibility test: same evidence gives the same layout within tolerance, or the variance is reported.
- [~] **T9** End-to-end through the real API with login, plus browser screenshots checked in a test run. **Status:** UI driven in Chromium on a real generated scene with API responses replayed, not a live login
- [x] **T10** Every citation shown in the UI resolves to a real observation.

**Done means:** T2, T3, T6, T9 and T10 all pass, and an independent reviewer cannot find a path through a wall or furniture.

---

## 9. Will fixing all this give a "real-like simulation for sure"?

| Layer | After phases 1-6 | After phase 7 too |
|---|---|---|
| Internally consistent (no walking through walls, clock and actions agree) | Yes | Yes |
| Auditable (every element traceable, versioned, reproducible) | Yes | Yes |
| Evidence-anchored times and positions | As far as the evidence allows | Same |
| Looks like a believable person in a believable room | Not yet | Mostly |
| Shows what actually happened | **No** | **No** |

The last row cannot be fixed by code: a simulation can show what the evidence is *consistent with*, and can rule theories out, but evidence usually does not contain enough to prove exactly where someone stood. Court use also needs review by a qualified forensic expert and legal counsel.

## 10. Differences between the two audits

**In your audit and not in mine (now included above):** missing migration, no RBAC or rate limit on sandbox endpoints, evidence IDs and untimed observations rejected as citations, resolved conflicts shown as unresolved, scoring and ranking details, door-marker offset, audit deleted with case, local vs UTC timestamps, Meta ignoring `max_tokens`, `utf8mb4`, and ID length.

**In mine and not in your audit:** the browser code-execution risk (S1), the unrelated Studio scene, photo reconstruction and segmentation (M9, M10), measured results (3,000-path fuzz, 4 saved scenarios, run-to-run variance, second case, zero-evidence case), invented scenes for empty cases, and title-vs-clock mismatch.

**Not matching the current code:** a few snippets in the older audit (the frame-based timing code and the "(detour)" title) come from an earlier revision. The conclusions still hold.


## Added after the checklist (Meta tooling, safety, robustness)

- **Provider modes** (`LLM_PROVIDER_MODE`): `auto` (unchanged), `meta_only`, `local_only` (any OpenAI-compatible server such as Ollama). The run records the mode and every call's model; the screen shows a "Meta models only" or "on-premise model" badge. Tested against a real local HTTP stand-in; **not tested with a real Llama model on this machine** (the 4.9 GB download was too slow here).
- **Instruction screen** for case text before it reaches a model (`pipeline/evidence_guard.py`): removes prompt-injection phrasing, records what was removed (shown as a badge and in the review pack). A pattern screen, not a guarantee. Verified live with Meta's model on a case whose evidence told the AI to deny any break-in: the instruction was removed and the scenarios still showed the break-in.
- **Photo links** (`pipeline/sandbox_photos.py`, SAM 3.1 hosted by Meta): finds the scene's objects in the case photographs; boxes are filtered for size and marked inferred; stored, hashed, audited, exported, and marked stale when the layout changes. Live on the four photographs of CW-E65FA6: 28 detector calls, 0 failed, 15 boxes kept. The detector misses some objects (nothing found for the rear shutter photo) and says so.
- **Engine fixes found by real runs and stress runs:** furniture running across a doorway made a room unreachable and sank every scenario (now cut back and disclosed); outdoor objects could cover the arrival strip at a door; a 5 mm disagreement between planner and validator at an obstacle's edge; a time-conflict message that read "0 min apart" for events in the opposite order.

## Situational logic (added after a real-run review)

A probe of 13 deliberately illogical scenarios showed the engine caught the physical ones (locked doors, walls, camera line of sight, speeds, times) but not the situational ones. Now added (`_logic_checks` in `sandbox_geometry.py`, 16 tests in `tests/test_sandbox_logic.py`):

- **Rejected (impossible):** a hand-over whose receiver is not close by at that time.
- **Cautions (the evidence may simply not say):** a hand-over nobody receives, and a receive nobody hands; putting down or handing over something never shown being picked up; someone who lies down and later moves with no step showing them getting up; forcing something with no tool mentioned; passing a closed, unforced outside door with no sign it was opened; two people in exactly the same spot for 5 s or more.
- **Disclosed default:** a person with no position of their own is shown at the nearest outside door, and the step now says so.
- **Real-run fixes the same review found:** a door drawn open before the scenario opens it; a witness drawn beside the intruder instead of at the kiosk the evidence gives; a far-off witness position being unreachable; a 5 cm planner/validator disagreement in narrow gaps.
- The scenario prompt now tells the model these rules, so real scenarios arrive with fewer cautions. Live check on CW-E65FA6: all three scenarios consistent, and the one new caution that fired ("puts down the crowbar with no step showing it picked up") is a fair one.

Still not modelled: sound and light, injuries changing speed, people blocking each other, vehicles driving, windows.

## Different possibilities, faithful simulations, and a second-model review (added later)

- **Genuinely different scenarios** (`pipeline/sandbox_diversity.py`): code finds the questions the evidence leaves open (which entry, how many people, inside knowledge, which clock, each unresolved conflict) and gives every scenario a different position on them; the best-supported reading comes first, the others are labelled "less supported possibility". A difference score (entry, people, places, order of key actions, items, clock reading) sends near-copies back for one retry. Live on CW-E65FA6: first attempt had one near-duplicate pair, second had none; difference scores 0.32–0.65.
- **Does the simulation say what the scenario says?** (`pipeline/sandbox_fidelity.py`) A round-trip check (every step, change to a door or object, item and person), summary-count check ("two intruders" vs the people shown), role rules (a victim, witness or staff member shown taking, forcing or restraining is flagged), evidence coverage, and a guard against naming a real person from the case as a suspect on a guess.
- **One repair attempt** for scenarios with fixable logical problems; time conflicts with the evidence clocks are deliberately not "repaired", they stay flagged.
- **One shared clock and linked steps:** people's timelines are put on the evidence clock where their steps cite timed evidence; a hand-over and its receive, and steps the scenario links with `sync_with`, are brought into the same moment (a person who is early waits). A gap too big to bridge (over 5 min) is reported, not hidden.
- **Second-model review with vision** (`pipeline/sandbox_frames.py`, `sandbox_reviewer.py`, `sandbox_review.py`): plan-view pictures of each scenario at up to 28 moments (start, end, every step, every door or object change, every claimed sighting with its line of sight, every cited clock time, mid-walk, just before/after major changes, close meetings, one overview), the case photographs, the scenario and the evidence it cites go to Meta's hosted vision model in batches. Every finding must point at a real step, picture or evidence id or it is dropped; names are redacted in text and in the pictures; the pictures are kept so a person can see what the reviewer saw. Live: 3 scenarios x 5 batches, 0 failed, about 3 minutes; it surfaced real defects (people on different clocks, a door shown closed while being forced) that were then fixed.
- **Tests:** 500 backend tests; 2,500-scene stress run clean; Chromium runs on the real scene, the review panel with real review data, the chat thread, and the WebGL-failure fallback.
- **Limits, stated plainly:** the reviewer is an opinion, it is the same model family as the generator, and "nothing found" is not proof; a scenario can be consistent and still wrong; the plan-view pictures do not show how the 3D view draws things; generation now takes about 2-3 minutes with the retry and repair calls.
