# CaseWeave Virtual Crime Scene Sandbox — Complete Issue Audit

> **Scope:** `backend/pipeline/sandbox.py`, `backend/db.py`, `backend/api.py`,
> `backend/pipeline/timeline.py`, `backend/pipeline/observe.py`,
> `backend/llm_client.py`, `backend/auth.py`,
> `frontend/app/scene/ForensicSandboxPlayer.tsx`,
> `frontend/app/case/[caseId]/page.tsx`, `frontend/app/lib/api.ts`.
>
> **Method:** full source read, schema comparison against `HEAD`, manual trace of
> every generated field from evidence → LLM → validation → persistence → API →
> frontend, and sample-case cross-check.
>
> **No code was changed by this audit.** This document is analysis only.

---

## Table of contents

1. [Verdict](#verdict)
2. [What is genuinely solid](#what-is-genuinely-solid)
3. [Severity legend](#severity-legend)
4. [P0 — breaks the stated guarantees](#p0--breaks-the-stated-guarantees)
5. [P1 — layout generation and validation](#p1--layout-generation-and-validation)
6. [P1 — scenario generation](#p1--scenario-generation)
7. [P1 — physics and geometry](#p1--physics-and-geometry)
8. [P1 — persistence, database, API](#p1--persistence-database-api)
9. [P1 — frontend and UI correctness](#p1--frontend-and-ui-correctness)
10. [P1 — LLM robustness, security, legal](#p1--llm-robustness-security-legal)
11. [P2 — minor correctness and polish](#p2--minor-correctness-and-polish)
12. [Testing gaps](#testing-gaps)
13. [What “real-world perfect” requires](#what-real-world-perfect-requires)
14. [Recommended remediation order](#recommended-remediation-order)
15. [Appendix A — claims vs. reality](#appendix-a--claims-vs-reality)
16. [Appendix B — file map](#appendix-b--file-map)

---

## Verdict

The rewrite is a real improvement over the hardcoded demo:

- The LLM no longer emits coordinates.
- Node IDs are resolved server-side.
- Some physics is deterministic math.
- Results are cached per case.
- There is no hardcoded case ID in the sandbox pipeline.

But it does **not** meet the stated guarantees. The biggest problems are not
cosmetic — they break the audit story:

1. **“Wall-safe by construction” is false.**
2. **The animation, action, position, and clock model is desynchronised.**
3. **Untraceable geometry is still allowed.**
4. **Evidence-fit is LLM opinion, not evidence scoring.**
5. **The single-room/single-actor data model cannot represent most real cases.**

A court-facing reconstruction must be correct, contestable, and inspectable.
This implementation is still closer to an evidence-themed animation than an
auditable reconstruction.

---

## What is genuinely solid

These parts should be kept and built upon:

- **LLM does not emit coordinates.** The model emits node IDs, fractions,
  dimensions, and actions; the backend resolves world positions
  (`sandbox.py:294-301`).
- **Node-ID whitelist.** Unknown step node IDs are dropped rather than invented
  (`sandbox.py:588-590`).
- **Deterministic AABB fixture test.** The slab test in
  `_point_in_fixture`/`_segment_enters_box` (`sandbox.py:451-486`) is real
  geometry, not an LLM guess.
- **Single-pass auto-detour.** The code at least attempts to push paths around
  fixtures (`sandbox.py:500-552`).
- **Per-case caching.** Layout and scenarios are persisted and reused
  (`sandbox.py:318-328`, `890-928`).
- **Audit hooks.** Layout/scenario generation writes audit events
  (`sandbox.py:312`, `884-887`, `918`).
- **Shared evidence context.** Layout and scenario generation reuse the same
  evidence summary (`sandbox.py:89-118`).
- **Frontend is largely data-driven.** Room, fixtures, doors, key locations,
  frames, and actions come from the payload; there is no per-case JSX.

---

## Severity legend

| Level | Meaning |
|---|---|
| **P0** | Breaks a core promise; unsafe for court or production; must fix before use. |
| **P1** | Serious correctness, auditability, or usability defect. |
| **P2** | Robustness, edge case, or polish. |

---

# P0 — Breaks the stated guarantees

## P0-1. Existing databases break on upgrade (no migration)

`CREATE TABLE IF NOT EXISTS case_sandbox_scenarios` (`db.py:174`) does **not**
add new columns to an existing table. The current code inserts `badge`,
`supporting_facts_json`, `contradicted_points_json`, `node_sequence_json`, and
`provider`, but a database created before those columns existed has none of
them. Every `REPLACE INTO` in `_persist_scenarios` (`sandbox.py:716-731`) then
fails with “Unknown column.”

Evidence the old schema lacked these columns:

```text
git show HEAD:backend/db.py
```

The `HEAD` version of `case_sandbox_scenarios` has only:

```text
scenario_id, case_id, scenario_type, title, hypothesis_summary,
evidence_fit_pct, physics_validation_json, frames_json, trajectory_json,
scene_config_json, interview_qa_json, computed_at, created_at
```

There is no `ALTER TABLE`, no migration framework, and `init_db()` only creates
missing tables (`db.py:273-278`). `case_sandbox_layout` is entirely new, so it
will be created on existing installs, but the scenario table will not be
upgraded.

**Impact:** any existing deployment cannot persist sandbox scenarios after this
change.

---

## P0-2. “Wall-safe by construction” is false

The code claims:

> “every exterior<->interior transition is auto-routed through the nearest real
> entry_point first — making every rendered path provably wall-safe by
> construction” (`sandbox.py:560-568`).

The actual implementation does not guarantee this.

### P0-2a. Fixed exterior spawn

The synthetic exterior node is hardcoded at:

```python
[0, 0, -(length_m / 2 + 3)]
```

(`sandbox.py:437`)

That is always south of the building, on the room’s centre axis. It has no
relationship to where the evidence says the actor came from.

### P0-2b. Exterior-to-door leg is never collision-checked

`_avoid_fixture_collisions` skips any segment touching an exterior node:

```python
if prev.get("is_exterior") or cur.get("is_exterior"):
    i += 1
    continue
```

(`sandbox.py:522-525`)

The auto-inserted exterior→door leg is therefore never corrected.

### P0-2c. Door routing can still cross walls

The auto-routing picks the nearest entry point to the interior node
(`sandbox.py:604-605`). The path is then:

```text
exterior spawn (south centre) → door → interior node
```

- If the chosen door is on the **north** wall, the exterior spawn → door
  segment crosses the south wall, the whole room, and the north wall.
- If the chosen door is on the **east** or **west** wall, the segment crosses
  at least one perimeter wall.
- If the chosen door is on the **south** wall but offset from centre, the
  segment crosses the south wall plane outside the door aperture.
- The door → interior leg can also cross interior fixtures or walls because
  only fixtures are checked, not wall segments.

### P0-2d. Physics checks points, not segments

`calculate_physics_validation` only checks waypoint **points** against room
bounds (`sandbox.py:359-371`). It never tests:

- segment vs. wall
- segment vs. door aperture
- segment vs. closed door/shutter
- segment vs. fixture (the detour is not re-validated)

A path can pass through a wall and still report `is_physically_possible: true`.

**Impact:** the exact bug the rewrite claims to eliminate still exists.

---

## P0-3. Timeline, action, position, and clock are desynchronised

`dt_sec` has no consistent meaning across backend and frontend.

### P0-3a. Backend accumulates before storing

The backend calculates:

```python
dt_sec = ...
clock_seconds += dt_sec
trajectory.append({..., "dt_sec": dt_sec})
frames.append({"elapsed_sec": clock_seconds, ...})
```

(`sandbox.py:619-634`)

So `elapsed_sec` is the time **after** the node’s `dt_sec`, not the time the
actor arrives.

### P0-3b. Physics uses the destination’s `dt_sec`

```python
dt = waypoints[i + 1].get("dt_sec", 30)
speed = dist / max(dt, 1)
```

(`sandbox.py:346-347`)

The segment from node `i` to node `i+1` is timed by node `i+1`’s duration.

### P0-3c. Frontend uses the source’s `dt_sec`

```typescript
const dt = frame?.elapsed_sec
  ? Math.max(0.5, frame.elapsed_sec - (frames[i - 1]?.elapsed_sec ?? 0))
  : Math.max(0.5, waypoints[i]?.dt_sec ?? 4);
```

(`ForensicSandboxPlayer.tsx:283-288`)

The segment from `i` to `i+1` is timed by node `i`’s duration.

### P0-3d. Total duration differs

- Backend: `total_dt = sum(w.dt_sec for w in waypoints[1:])`
  (`sandbox.py:356`) — excludes the first node.
- Frontend: `totalDuration = sum(w.dt_sec)` over all waypoints
  (`ForensicSandboxPlayer.tsx:244`) — includes the first node.

### P0-3e. Actions happen during transit

At `t=0`, frame 0 is selected and the actor is already moving toward node 1 for
frame 0’s `dt_sec` (`ForensicSandboxPlayer.tsx:283-304`). The actor never dwells
at node 0 while “searching” or “taking” anything. Every non-move action
(`search`, `take_item`, `struggle`, `damage`) is visually performed while
walking.

### P0-3f. Milestones jump to the wrong frame

Frames use cumulative end times; clicking frame `i` sets `simTime` to
`frames[i].elapsed_sec`. The segment loop has already advanced to `i+1` at that
boundary (`ForensicSandboxPlayer.tsx:283-296`, `967`). Clicking “Counter” can
show “Aisle 3.”

### P0-3g. Detour frames duplicate timestamps

`_avoid_fixture_collisions` copies the destination frame’s `elapsed_sec` and
`disturbed_nodes`:

```python
detour_frame = {
    **frame,
    "frame_idx": len(adjusted_frames),
    "actor": {"pos": detour},
    "title": f"{frame['title']} (detour)",
    "narrative": (frame.get("narrative") or "") + " (routed around an obstacle)",
}
```

(`sandbox.py:539-550`)

Two frames can share the same `elapsed_sec`; a detour can expose the
destination’s future disturbances before arrival.

### P0-3h. Last-node dead time

The frontend keeps simulating after the last segment because the last waypoint’s
`dt_sec` is unaccounted for, while the backend excludes it from total duration.

**Impact:** the clock, the highlighted step, the actor position, the action
animation, and the physics verdict do not agree.

---

## P0-4. Evidence traceability is not enforced

The stated rule is: “Nothing drawn that isn’t traceable; `evidence_refs` on
every node.”

### P0-4a. Empty refs are accepted and rendered

`_validate_layout` accepts nodes with empty `evidence_refs`
(`sandbox.py:180-183`, `205`, `232`, `251`). The frontend renders them normally
(`ForensicSandboxPlayer.tsx:974-984`).

### P0-4b. Fabricated entry point

If the LLM returns no valid entry point, the code invents:

```python
{
    "id": "main_entry",
    "label": "Main Entrance",
    "wall": "south",
    "position_frac": 0.5,
    "width_m": 1.0,
    "evidence_refs": [],
}
```

(`sandbox.py:207-209`)

Also defaults:

- `width_m = 10.0`
- `length_m = 10.0`
- `height_m = 3.0`
- `wall = "south"`

(`sandbox.py:185-204`)

### P0-4c. Wrong `known_ids` for citations

For layout validation, `known_ids` is:

```python
{obs_id for timeline_events} | {entity_id for entities}
```

(`sandbox.py:176`)

Problems:

- The prompt shows evidence items as `[evidence_id]` (`sandbox.py:97`), but
  evidence IDs are **not** in `known_ids`. A legitimate citation to
  `EV-...` is silently stripped.
- Observations **without `extracted_time`** never enter `timeline_events`, so
  they are not in `known_ids`. A case whose observations are untimed gets zero
  valid observation citations.
- `_gather_case_evidence` loads `observations` (`sandbox.py:61`) but
  `_evidence_context_text` never uses them (`sandbox.py:89-118`).
  The LLM never sees untimed observations at all.

For scenario validation, `known_ids` is only:

```python
{source_observation_id for timeline_events} | {entity_id for entities}
```

(`sandbox.py:663`)

Same untimed-observation gap.

### P0-4d. Citation validation is existence-only

`_clean_refs` checks that an ID exists somewhere in `known_ids`
(`sandbox.py:257-265`). It does not verify:

- the cited observation actually supports the node;
- the citation is about the right object/person/location;
- the citation is not contradicted elsewhere;
- the citation points to a real source location.

A real but unrelated ID passes as “grounded.”

### P0-4e. No source locator in output

The DB has `observations.source_locator` (`db.py:60`), but the sandbox prompt
and output never include it (`sandbox.py:95-118`, `257-265`). The UI can show
“OBS-004,” but not the file, page, paragraph, or frame.

### P0-4f. Resolved conflicts are treated as unresolved

`_gather_case_evidence` selects **all** conflicts (`sandbox.py:60`) and the
prompt labels them “UNRESOLVED CONFLICTS” (`sandbox.py:113-116`).
`review_status` is ignored. A conflict that the officer already resolved still
weakens/fogs every scenario.

### P0-4g. Semantic citation validation of narratives is absent

`supporting_facts` and `contradicted_points` are free text. Bracketed IDs are
never parsed or checked against `known_ids` (`sandbox.py:694-695`). A narrative
can cite a non-existent observation and still be displayed.

**Impact:** “grounded in evidence” is not guaranteed; fabricated geometry and
fake citations can reach the UI.

---

## P0-5. Path segments are neither rendered nor auditable

The stated goal is: “Click any object/path segment and see which evidence
justified it.”

### P0-5a. No path is rendered

The scene contains room, fixtures, key-location rings, and the actor:

```tsx
<RoomShell layout={layout} />
<KeyLocations layout={layout} ... />
<FixtureObjects layout={layout} ... />
<Actor ... />
```

(`ForensicSandboxPlayer.tsx:974-984`)

There is no trajectory polyline, no segment marker, and no “auto-inserted” path
highlight.

### P0-5b. Walls are not clickable

The UI says “Click any wall or object to see the exact evidence that justified
its geometry” (`ForensicSandboxPlayer.tsx:988-990`), but
`WallWithApertures` has no click handler (`ForensicSandboxPlayer.tsx:492-575`).
Only fixtures and key-location rings are clickable (`573`, `672`, `937`).

### P0-5c. `auto_inserted` is invisible

`auto_inserted` exists only on the TypeScript frame type
(`ForensicSandboxPlayer.tsx:67`). It is never rendered, never stored on
trajectory points, and never shown in the step list.

### P0-5d. Inserted hops are not in `node_sequence`

`scenario["node_sequence"] = steps` stores the original LLM steps, not the
resolved/auto-routed sequence (`sandbox.py:696`). A reviewer inspecting the
stored scenario cannot see the code’s routing corrections.

### P0-5e. Evidence refs are opaque IDs

The step list renders raw observation IDs:

```tsx
<span>Evidence: {step.evidence_refs.join(", ")}</span>
```

(`ForensicSandboxPlayer.tsx:1010-1014`)

No observation description, source filename, source locator, quote, or link to
the evidence viewer.

**Impact:** the path and its justification cannot be inspected, which defeats
the auditability requirement.

---

## P0-6. Physics does not validate fixture/wall safety

### P0-6a. No segment-vs-wall test

Physics checks only waypoint points (`sandbox.py:359-371`). A straight segment
between two valid points can cross a wall or a fixture.

### P0-6b. Fixtures are accepted as step targets

The scenario prompt says “ONLY the given layout node ids” and describes entry
points/key locations (`sandbox.py:386-420`), but `_layout_nodes_context` also
lists fixtures (`sandbox.py:430-431`) and `_known_node_ids` includes them
(`sandbox.py:443-444`). The LLM can therefore end a step inside a counter,
locker, or shelving unit.

Endpoint-inside-fixture is not checked anywhere.

### P0-6c. Detour is single-pass and can fail

`_avoid_fixture_collisions` inserts one detour point per collision
(`sandbox.py:500-552`). The two replacement segments can:

- hit the same fixture again;
- hit a different fixture;
- place the detour point near/inside a wall;
- place the detour point inside another fixture;
- be blocked by a second obstacle.

There is no iterative search, no visibility graph, no A*, and no final
segment/wall validation.

### P0-6d. Fixtures can protrude through walls

Fixture positions are clamped to fractions of `(width - 2*margin)` but the
fixture’s half-footprint is not considered (`sandbox.py:226-230`, `276-279`).
A 4 m-wide fixture in a 3 m room is accepted. Fixtures can overlap walls,
doors, key locations, and each other.

### P0-6e. Dimension inconsistencies

- Fixture height up to 2.5 m while room height can be 2.4 m
  (`sandbox.py:230`, `45`).
- Door width up to 4 m in a 3 m wall (`sandbox.py:204`, `44`).
- No minimum aisle/clearance.
- No door-width/height vs. actor check.

### P0-6f. No reachability or line-of-sight

- No check that every key location is reachable from a door.
- No wall/door occlusion.
- No camera/observer line-of-sight.
- The page claims “optical line-of-sight checks”
  (`page.tsx:1146`), but line-of-sight appears only as an interview question
  label (`sandbox.py:773-804`).

### P0-6g. Unrealistic motion constants

- `MAX_HUMAN_SPEED_MPS = 7.5` (`sandbox.py:47`) is a sprint speed applied to
  every action and actor.
- `WALL_MARGIN_M = 0.35`, `10 m` exterior margin, `4 s` detour, `8 s` door,
  and `5–600 s` step duration are arbitrary (`sandbox.py:44-47`, `363`, `454`,
  `529`, `608`, `621`).
- No acceleration, turn radius, crouch, injury, carrying, or forced-entry
  speed model.

**Impact:** physics PASS/FAIL is not a reliable test of the rendered scene.

---

## P0-7. “Top-3 evidence-fit-ranked” is not implemented

### P0-7a. Score is uncalibrated LLM opinion

`evidence_fit_pct` comes directly from the LLM (`sandbox.py:680`) with no
rubric, no deterministic support/contradiction count, and no calibration.

### P0-7b. Contradictions do not affect the score

Only physics failure caps the score:

```python
if not physics["is_physically_possible"]:
    fit_pct = min(fit_pct, 30)
```

(`sandbox.py:681-682`)

`contradicted_points` do not reduce fit. This contradicts the stated rule that
“physics is evidence against a theory, same as a contradiction is.”

### P0-7c. No sorting

Scenarios are never sorted by `evidence_fit_pct` after validation
(`sandbox.py:668-704`). Order is the LLM’s order.

### P0-7d. Badge is positional, not rank-based

```python
badge = "⭐ Primary Theory" if i == 0 else (
    "⚠️ Alternative Theory" if i == 1 else "ℹ️ Additional Theory"
)
```

(`sandbox.py:684`)

A physically impossible scenario can still be labelled “⭐ Primary Theory”
because `i == 0`, even when its score is 30 and another scenario scores 90.

### P0-7e. Original score is lost

The LLM score is overwritten by the cap. The user cannot see “LLM estimated
95, reduced to 30 by physics.”

### P0-7f. Reload order is not rank order

Automated rows are loaded by `created_at ASC` (`sandbox.py:900-903`), not by
fit or badge. On reload the primary theory may not be first.

### P0-7g. Unknown steps silently reduce coverage

Unknown node IDs are dropped (`sandbox.py:588-590`) with no `dropped_steps`,
no coverage penalty, and no user-visible warning. A scenario that lost half its
path can still be ranked #1.

### P0-7h. Scenario IDs depend on post-filter index

`scenario_id = f"SCEN-AUTO-{i + 1}-{case_id}"` uses the loop index after
`continue` (`sandbox.py:687`). If scenario 1 is dropped, the former scenario 2
becomes `SCEN-AUTO-1` and “Primary.”

**Impact:** ranking and “Primary Theory” are not evidence-derived, and are not
stable across generation/reload.

---

## P0-8. The data model cannot represent most real cases

### P0-8a. One rectangular room

`SandboxLayout` has one `width_m`, `length_m`, `height_m`, and a flat list of
fixtures/key locations (`ForensicSandboxPlayer.tsx:48-56`). There are no rooms,
floors, internal walls, or spaces.

### P0-8b. No internal doors/walls

`entry_points` are only perimeter apertures (`sandbox.py:143-147`,
`261-279`). The sample case describes a “secured internal dispensary” and a
“stockroom aisle 3”; the actor can walk straight through the internal wall
because it cannot exist in this model.

### P0-8c. One actor

`frames.actor` is singular (`sandbox.py:619-642`); one trajectory. There is no
support for:

- accomplices;
- victim;
- guard/witness;
- camera/observer;
- multiple simultaneous paths.

### P0-8d. No outdoor/urban/vehicle scene

No street, yard, fence, vehicle, multi-building, stairs, or multi-level
geometry.

### P0-8e. No body/object state

There is no victim position/orientation, no body pose, no object placement.
“Disturbed” is a boolean-derived visual tilt, not a state.

### P0-8f. No unknown geometry

The entire rectangle is traversable. There is no “unknown” or “not observed”
space, so the simulation implicitly asserts the whole room is known.

**Impact:** the generator is structurally unable to model many real cases, and
will silently simplify them into a single room.

---

## P0-9. “Real timeline” is only a start anchor

### P0-9a. Start-clock source is arbitrary

`_case_start_clock` returns the first non-empty timeline time string
(`sandbox.py:76-86`, `666`). That might be the report time or discovery time,
not the event start.

### P0-9b. Intermediate times are fabricated

`clock_seconds` is start + LLM-estimated `dt_sec` (`sandbox.py:616-634`). It is
not anchored to:

- witness statements;
- CCTV timestamps;
- alarm/access-control logs;
- the evidence time window;
- the NVR clock offset.

“Walks to counter at 01:22” is still an invented time.

### P0-9c. No source clock offsets

The sample case’s NVR is +5m32s. The sandbox has no notion of source clock
offsets, so generated times cannot be matched to CCTV. See the sample README.

### P0-9d. No date/timezone/seconds

The start clock is `HH:MM` only (`ForensicSandboxPlayer.tsx:263-266`). No date,
timezone, or seconds. `% 24` silently wraps midnight
(`ForensicSandboxPlayer.tsx:267`).

### P0-9e. Timeline ordering is string-based

`timeline.py:53` orders by `event_time` as a string. `9:05` sorts after `10:00`.

### P0-9f. No window validation

No check that the scenario duration fits a known evidence interval (e.g. CCTV
02:28:15–02:35:32) or a witness-estimated window.

### P0-9g. Custom hypothesis time is ignored

The custom hypothesis may say “at 23:45,” but the scenario always uses the
case-wide earliest time (`sandbox.py:881`).

**Impact:** the clock is not a real, evidence-anchored timeline; it is a
plausible-looking animation clock.

---

## P0-10. The sandbox API is a synchronous, under-protected GET with side effects

### P0-10a. GET mutates and generates

`GET /cases/{case_id}/sandbox/scenarios` generates and writes on a GET
(`api.py:545-554`). It is not idempotent and can be triggered by prefetch,
crawlers, or accidental reloads.

### P0-10b. No RBAC

There is no `enforce_permission(user, "view_case")` or `upload_evidence` on the
sandbox endpoints (`api.py:545-579`). Any authenticated role can generate and
spend LLM budget on any case. The auth module is role-based only
(`auth.py:43-53`).

### P0-10c. No rate limit

`/process` and `/chat` are rate-limited; the sandbox endpoints are not
(`api.py`, grep for `limiter`). A user can repeatedly force-regenerate.

### P0-10d. Synchronous LLM in the request

Layout + 3 scenarios can take 30–60s+ and block the request. There is no job
queue, progress, or cancellation.

### P0-10e. Retry amplification

`chat_json` retries up to 3 times per provider across up to 3 providers
(`llm_client.py:41-65`, `257-278`). A bad request can stall for minutes.

### P0-10f. Everything is HTTP 500

All errors become `HTTPException(500, str(e))` (`api.py:553-554`, `565-566`,
`578-579`). This conflates:

- LLM unavailable (should be 503);
- no evidence / insufficient evidence (422);
- permission denied (403);
- programming error (500).

### P0-10g. Frontend swallows the error

```typescript
api.getSandboxScenarios(caseId).catch(() => ({ scenarios: [], layout: null }))
```

(`page.tsx:201`)

The player then shows “Generating…” forever because
`scenarios.length === 0` (`ForensicSandboxPlayer.tsx:862-870`). There is no
empty/error state.

### P0-10h. Sandbox blocks all case data

The sandbox request is inside `Promise.all` with timeline, conflicts, entities,
and audit (`page.tsx:195-202`). The first page load waits for the LLM before
showing any case data.

### P0-10i. No timeout/abort

The frontend fetch has no `AbortController` (`api.ts:35-59`); there is no
server-side timeout for the LLM call.

**Impact:** a slow or failing sandbox degrades the whole case page, and any
authenticated user can trigger unbounded generation.

---

## P0-11. Cache consistency, staleness, and versioning

### P0-11a. Empty-case prefetch poisons the cache

`loadAll()` calls `refreshDerived()` on mount (`page.tsx:176-190`), which calls
the sandbox endpoint. For a new case with no pipeline output, the sandbox
generates a generic 10×10 room and scenarios and caches them
(`sandbox.py:282-328`).

After the pipeline finishes, `refreshDerived` sees the cached automated rows and
returns the **pre-evidence** scenario until the user manually clicks Regenerate.

### P0-11b. New evidence never invalidates the cache

There is no evidence-set fingerprint/hash. `case_sandbox_layout` stores only
`generated_at` (`db.py:195-203`). Uploading new evidence leaves the old layout
and scenarios in place.

### P0-11c. New layout with old scenarios on failure

`get_sandbox_scenarios` writes the new layout **before** generating scenarios:

```python
layout = generate_case_layout(case_id)
scenarios = generate_evidence_grounded_scenarios(case_id, layout)
```

(`sandbox.py:897`, `914`)

If scenario generation fails, the new layout is saved and the old scenarios
remain, so the next non-force GET pairs a new layout with stale positions.

### P0-11d. Custom scenarios are never invalidated

When the layout changes, custom scenarios keep their old hardcoded positions
(`sandbox.py:904-907`, `921`).

### P0-11e. No schema/version field

`layout_json`, `frames_json`, and `trajectory_json` have no schema version.
Old cached shapes are returned without revalidation (`sandbox.py:318-328`) and
can crash the frontend (missing `pos`, old `scene_config_json`).

### P0-11f. No concurrency control

Two concurrent first-load requests both generate. Concurrent force recomputes
race on `DELETE`/`REPLACE` (`sandbox.py:707-733`, `896-919`). There is no lock,
idempotency key, or transaction isolation policy.

### P0-11g. `REPLACE` destroys history

`REPLACE INTO` deletes and reinserts, overwriting `created_at` and discarding
the prior row. Combined with `DELETE` for automated scenarios
(`sandbox.py:713`), regeneration erases prior artifacts.

### P0-11h. Partial persistence

`_persist_scenarios` does not wrap inserts in explicit error cleanup; a failure
mid-loop can leave a partial set. `conn.close()` is not in `finally`.

### P0-11i. ID length overflow

`scenario_id = f"SCEN-AUTO-{i+1}-{case_id}"` (`sandbox.py:687`) can exceed
`VARCHAR(64)` (`db.py:175`) for long case IDs.

**Impact:** users can see scenarios that do not correspond to the current
evidence/layout, and regeneration is not reproducible or safe.

---

## P0-12. Court-grade audit is missing

### P0-12a. No immutable versions

Regeneration deletes prior automated scenarios (`sandbox.py:713`). A defence
lawyer cannot see what was generated and discarded, enabling “regenerate until
favourable.”

### P0-12b. No content hashes

Audit events record only counts/providers (`sandbox.py:312`, `918`), not a hash
of the layout/scenario content. DB rows can be edited directly with no
detection.

### P0-12c. User attribution is hardcoded

The custom-scenario audit hardcodes `"investigator"`:

```python
append_audit_event(conn, case_id, "investigator",
                   "sandbox_custom_scenario_generated_via_llm", ...)
```

(`sandbox.py:886`)

The actual user/role is available at the API layer but not passed down.

### P0-12d. Interview Q&A is not stored

`interview_qa` stores only answers (`sandbox.py:879`), and the synthesis prompt
sends only answers (`sandbox.py:838`). The questions and the reasoning chain
are reconstructable only from static code.

### P0-12e. Model/provider/prompt version not surfaced

`provider` is stored (`sandbox.py:700`, `729`) but not returned by
`_row_to_scenario` (`sandbox.py:736-762`) and never shown. The model name,
prompt version, temperature, and prompt hash are not stored anywhere.

### P0-12f. Third-party transmission is undisclosed

Full evidence, including witness statements and PII, is sent to third-party LLM
providers (`llm_client.py:134-138`). The sandbox UI does not disclose this,
offer redaction, or record consent.

### P0-12g. No court export

There is no exportable audit pack containing:

- layout + provenance;
- citations + source locators;
- physics report;
- version history;
- content hashes.

**Impact:** the artifact is not court-inspectable or tamper-evident.

---

# P1 — Layout generation and validation

- **Type-unsafe parsing can 500 the request.**
  `float(raw.get("width_m", 10) or 10)` and nested
  `(fx.get("footprint_m") or ...)` raise on `"10m"`, a list, a dict, or a short
  nested list (`sandbox.py:185-230`). No try/coerce helper.

- **No reserved IDs.**
  A fixture/entry point with id `exterior` overwrites the synthetic exterior
  node (`sandbox.py:436-444`), breaking boundary routing.

- **Global `seen_ids` across categories.**
  A fixture and key location may legitimately share the slug `counter`; the
  second is silently dropped (`sandbox.py:190`, `216`, `221`, `240`).

- **No enforcement of minimality.**
  The prompt says return a minimal layout when evidence is thin
  (`sandbox.py:162-164`), but the code always fabricates a door and default
  dimensions. There is no “insufficient evidence” response.

- **No provenance per node.**
  There is no `observed | reported | inferred | defaulted` flag, no confidence,
  and no rationale. `notes` is the only disclosure, capped at 400 chars
  (`sandbox.py:257`), and never shown in the UI.

- **`notes` is lost.**
  The frontend type declares it (`ForensicSandboxPlayer.tsx:55`) but never
  renders it.

- **No evidence-coverage metric.**
  The UI cannot say “this layout is based on 2 of 9 evidence items” or “these 4
  objects are defaults.”

- **No image/floor-plan use.**
  The layout LLM receives only text observations. Despite photos and vision
  models existing, room geometry is never derived from photos/plans
  (`sandbox.py:89-118`).

- **No scale/origin calibration.**
  Dimensions are LLM guesses clamped to 3–40 m. Nothing anchors the coordinate
  frame to a real plan, landmark, or measured distance.

- **Truncation is silent.**
  `timeline[:60]` (`sandbox.py:100`), `entry_points[:8]`, `fixtures[:30]`,
  `key_locations[:15]` (`sandbox.py:191`, `212`, `236`), `clean_refs[:8]`
  (`sandbox.py:183`). Later evidence/nodes disappear with no warning.

- **Prompt size is unbounded.**
  `evidence_items`, `entities`, `relationships`, and `conflicts` have no caps
  or per-line truncation (`sandbox.py:95-117`); large cases can exceed provider
  context or blow the token budget.

- **Resolved conflicts are presented as unresolved** — see P0-4f.

- **No overlap/clearance validation** — see P0-6d.

- **No layout editor.**
  If the inferred room is wrong, the officer cannot correct a wall, door, or
  fixture; every scenario is built on the wrong layout. There is no
  human-in-the-loop geometry correction with provenance.

---

# P1 — Scenario generation

- **`supporting_facts`/`contradicted_points` type bug.**
  If the LLM returns a string instead of an array, the code iterates characters:
  `[str(s)[:300] for s in (raw.get("supporting_facts") or [])[:10]]`
  (`sandbox.py:694-695`). A dict iterates keys.

- **`steps` type bug.**
  If `steps` is a string, `_resolve_steps_to_trajectory` iterates characters
  and calls `.get` on a string → `AttributeError` → 500
  (`sandbox.py:578-589`).

- **`fit_pct` type bug.**
  `int(raw.get("evidence_fit_pct", 50) or 50)` raises on `"75%"` or `"75.5"`
  (`sandbox.py:680`, `860`).

- **`phase`/`title` not type-checked.**
  A dict/list `phase` is stored and later rendered by React, which can throw or
  render `[object Object]` (`sandbox.py:635`;
  `ForensicSandboxPlayer.tsx:301`, `925`).

- **No step-count cap.**
  An LLM can emit hundreds of steps; frames/trajectory/JSON payload and
  per-frame O(n) work grow without bound (`sandbox.py:619-641`).

- **No dropped-step disclosure.**
  Unknown node IDs are dropped (`sandbox.py:589-590`) but the scenario still
  reports the LLM’s original fit and narrative as if the whole path existed.

- **Fixtures accepted as step nodes** — see P0-6b.

- **`node_sequence` is raw, unvalidated LLM output.**
  It includes unknown IDs, arbitrary actions, and steps that were never
  rendered (`sandbox.py:696`). It is not the actual simulated sequence.

- **Per-step citations absent.**
  `frames` have no `evidence_refs`/`citations` field (`sandbox.py:632-642`).
  Only scenario-level `supporting_facts` exist, and bracket citations inside
  them are never validated against `known_ids`.

- **Auto-inserted door hop uses `action: "enter"` for exits too.**
  The narrative says “Passes through,” but the action is semantically wrong when
  leaving (`sandbox.py:607-609`).

- **Auto-routing chooses the nearest door, not the evidence-consistent door.**
  If evidence says entry was the rear shutter but the nearest interior node is
  near the front door, the system routes through the wrong door with no
  rationale beyond `auto_inserted` (`sandbox.py:604-605`).

- **No evidence-consistency validation.**
  A scenario can enter through a door the evidence says was intact/locked, pass
  a camera the evidence says covers the area, or happen outside the known time
  window. Only kinematics is checked.

- **No duration/window validation.**
  No comparison of scenario duration to CCTV/clip length or witness-estimated
  intervals (P0-9).

- **No multi-actor support** — see P0-8c.

- **Action vocabulary is too narrow.**
  Only `approach|enter|move|search|take_item|struggle|damage|flee|other`;
  unknown actions are silently forced to `move` (`sandbox.py:624-626`). No
  `drop_item`, `open`, `close`, `unlock`, `place`, `wait`, `hide`, `look`,
  `signal`, `drive`, etc.

- **Carrying state never clears.**
  Once any `take_item` occurs, `isCarryingItem` stays true for the rest of the
  scenario (`ForensicSandboxPlayer.tsx:307`); there is no drop/place action.

- **Disturbance is inferred only from three action strings.**
  `sandbox.py:627-628`. A fixture can be “disturbed” without any evidence
  citation, and the visual tilt direction/magnitude is arbitrary
  (`ForensicSandboxPlayer.tsx:620-623`).

- **Tool/bag props are not evidence-linked.**
  `holdsTool` is any struggle/damage (`ForensicSandboxPlayer.tsx:385`),
  rendered as a generic blue box; a “crowbar” or “duffel bag” in the evidence
  is not represented or cited.

- **No scenario-level status/rank/version fields.**
  No `rank`, `review_status`, `version`, `created_by`, `evidence_hash`,
  `model`, `prompt_hash`.

- **No retry/repair when the LLM returns fewer than 3 or malformed JSON.**
  `chat_json` only strips fences/trailing junk (`llm_client.py:281-302`);
  leading prose or truncated JSON fails.

- **Meta provider ignores `max_tokens`.**
  `_call_meta` never sends a max-output parameter (`llm_client.py:68-91`), so
  layout/scenario JSON can be truncated or unbounded regardless of the caller’s
  2048/3072 budget.

- **No reproducibility.**
  Temperature 0.2 (`llm_client.py:106`, `127`), provider fallback, no seed, no
  model version stored. A regenerate can produce a different reconstruction
  with no audit trail.

- **Prompt injection.**
  Evidence text and the officer’s hypothesis are inserted directly into prompts
  (`sandbox.py:285`, `652`, `840`) with no delimiters/escaping. A malicious
  document can instruct the model to invent geometry or citations.

- **No cross-scenario comparison.**
  The UI shows one scenario at a time; there is no table of fit, contradictions,
  physics, citations, or differing path assumptions. Custom scenarios are
  scored by a separate LLM call and are not comparable to automated ones.

---

# P1 — Physics and geometry

- **No segment-vs-wall / aperture intersection** — P0-2d.
- **Exterior spawn fixed to south** — P0-2a.
- **Speed uses the wrong `dt`** — P0-3b.
- **Total duration inconsistent** — P0-3d.
- **Single-pass detour** — P0-6c.

- **Detour not clamped to room or clear of other fixtures.**
  It uses a bounding circle and one perpendicular side; near a wall it can go
  outside, and near another fixture it can route into it
  (`sandbox.py:482-497`).

- **Detour endpoint can be inside the target fixture.**
  Fixture nodes are allowed and endpoint-inside is not checked.

- **No iterative path planning / visibility graph.**
  A single waypoint is not enough for a room with several obstacles; no A* or
  navmesh.

- **Fixtures are AABBs with no rotation.**
  The renderer tilts disturbed fixtures (`ForensicSandboxPlayer.tsx:622`), so
  the visual footprint changes while the collision model still uses the
  original AABB.

- **No actor capsule vs. door frame/wall thickness.**
  The backend treats walls as planes and doors as points; the frontend wall is
  0.3 m thick (`ForensicSandboxPlayer.tsx:489`).

- **No door state.**
  Apertures are always open. Evidence may say a shutter was forced/lifted, a
  door was locked, or a window was intact; the simulation cannot represent that.

- **No vertical physics or object dynamics.**
  “Disturbed” is a static tilt; no gravity, toppling, breakage, or item
  placement.

- **No line-of-sight/occlusion** — P0-6f.

- **Speed thresholds are not action-specific.**
  Walk/run/sprint/crawl, carrying a bag, injured, or forced entry all use the
  same 7.5 m/s ceiling.

- **`avg_speed_mps` includes dwell.**
  Total distance / total dt (`sandbox.py:356-357`), so the UI label “Transit
  Speed” is misleading.

- **Cached physics results are not revalidated.**
  `physics_validation_json` is returned as stored (`sandbox.py:757`); if the
  code’s rules change, old PASS/FAIL is shown.

- **No NaN/legacy guard.**
  Corrupt/old `layout_json` can produce `KeyError`/`TypeError`; `_clamp` is not
  a validator.

- **Arbitrary constants are presented as physics.**
  `7.5 m/s`, `0.35 m` clearance, `10 m` exterior margin, `4 s` detour, `8 s`
  door, and `5–600 s` step duration (`sandbox.py:44-47`, `363`, `454`, `529`,
  `608`, `621`) are magic numbers with no evidence or configuration.

---

# P1 — Persistence, database, API

- **No migrations** — P0-1.
- **No cache version/evidence fingerprint** — P0-11b.
- **Stale layout/scenario pairing on failure** — P0-11c.
- **Custom scenarios never invalidated** — P0-11d.
- **Concurrency race** — P0-11f.
- **`REPLACE` destroys history** — P0-12a.

- **No transaction rollback/cleanup in `_persist_scenarios`.**
  `conn.close()` is not in a `finally`; an exception can leak the connection and
  leave transaction state undefined (`sandbox.py:707-733`).

- **Audit after commit.**
  Layout/scenarios are committed before `append_audit_event`
  (`sandbox.py:306-313`, `732-733`, `884-887`); if the audit write fails, the
  artifact exists without an audit entry.

- **Local vs. UTC timestamps.**
  `time.strftime` is local (`sandbox.py:305`, `711`); `append_audit_event` uses
  `datetime.utcnow()` (`db.py:322`). The audit cannot reliably order events
  across timezones.

- **`_gather_case_evidence` leaks a connection on exception.**
  No `try/finally` (`sandbox.py:57-63`).

- **No case-existence/evidence-readiness check.**
  It generates on an empty case and on a partially processed case.

- **`case_sandbox_layout` has no `evidence_hash`, `schema_version`, `model`,
  `prompt_hash`, `generated_by`.**

- **`provider` not returned; `computed_at` not returned; `cached` ignored by
  UI.** (`sandbox.py:736-762`)

- **`badge` is `VARCHAR(64)` with emoji and text** (`db.py:178`);
  charset/truncation risk depending on server default. `title` is truncated to
  120 but the column is 128; `hypothesis_summary` is TEXT.

- **No delete/retract endpoint for custom scenarios; no dedupe/idempotency
  key.** Repeated synthesis creates duplicates.

- **No version endpoint/history; no “as-of” query.**

- **No export/print/PDF of the scenario audit pack.**

- **API error taxonomy is absent.**
  `500` for everything; `LLMUnavailableError` should be `503`, no-evidence
  `422`, permission `403`.

- **No request timeout/cancellation.**
  The frontend fetch has no `AbortController` (`api.ts:35-59`).

- **No per-case cost budget.**
  A user can repeatedly force-regenerate.

- **GET cacheability** — P0-10a.

---

# P1 — Frontend and UI correctness

- **Infinite spinner on empty/error** — P0-10g
  (`page.tsx:201`, `ForensicSandboxPlayer.tsx:862-870`).
- **`Promise.all` blocks all case data on the sandbox** — P0-10h
  (`page.tsx:195-220`).
- **No path rendering/click** — P0-5a (`ForensicSandboxPlayer.tsx:974-984`).
- **Walls not clickable despite the hint**
  (`ForensicSandboxPlayer.tsx:989`; `WallWithApertures` has no `onClick` at
  `492-575`).
- **Evidence refs are opaque IDs, not resolvable**
  (`ForensicSandboxPlayer.tsx:1010-1014`). No description, filename, locator, or
  link.
- **`auto_inserted` never surfaced** — P0-5c.
- **Layout `notes`/provenance never surfaced** — P1 layout.

- **Physics panel overstates coverage.**
  It shows “PASS” after only point-bounds/speed checks
  (`ForensicSandboxPlayer.tsx:1038-1058`); it does not tell the user that
  walls/fixtures/doors/line-of-sight were not tested.

- **Fit % presented as objective.**
  No “LLM estimate” label, no raw-vs-capped disclosure, no uncertainty.

- **Milestone/clock/action desync** — P0-3
  (`ForensicSandboxPlayer.tsx:283-304`, `860`, `967`).

- **`currentLabel` shows the node being left, not the node occupied.**
  During transit it displays the departing node (`ForensicSandboxPlayer.tsx:304`).

- **Custom scenario prepend shifts the active index.**
  `setSandboxScenarios((prev) => [res, ...prev])` (`page.tsx:229`) while
  `activeScenarioIdx` stays unchanged (`ForensicSandboxPlayer.tsx:756`), so the
  selected scenario silently changes.

- **Regenerate errors are silent.**
  `handleRegenerate` has no `catch` (`ForensicSandboxPlayer.tsx:845-856`);
  unhandled rejection, no UI message.

- **Interview errors are silent.**
  `handleStartInterview` only `console.error`s
  (`ForensicSandboxPlayer.tsx:821-824`); the user sees nothing.

- **Camera Reset can be a no-op.**
  If `cameraPreset` is already `"overview"`, `setCameraPreset("overview")` does
  not change state, so the effect does not re-run; the camera stays wherever it
  was (`ForensicSandboxPlayer.tsx:140-146`, `949`, `996`). Selecting a new
  scenario also clears `focusTarget` but does not restore the preset.

- **Interview is not Socratic/adaptive.**
  Exactly 3 fixed questions once (`sandbox.py:769-808`); answer chips only
  (`ForensicSandboxPlayer.tsx:1112-1124`); no free-text per question, no
  follow-up based on answers, no detection of which specific facts are missing.
  The officer cannot type “the crowbar was 18 inches” unless it is a predefined
  chip.

- **Questions are not sent to synthesis or persisted** — P0-12d.

- **No comparison view/overlay.**
  Only tabs; no side-by-side matrix or path overlay.

- **No provider/model/generated-at/staleness display.**

- **No ordered step list with rationale/citations.**
  `node_sequence` is typed as `unknown[]` and never rendered
  (`ForensicSandboxPlayer.tsx:87`).

- **Door markers are offset from the actual wall gaps.**
  Backend door positions are inset `WALL_MARGIN_M = 0.35` from the wall
  centerline (`sandbox.py:270-275`), while the frontend renders the aperture at
  the wall centerline (`ForensicSandboxPlayer.tsx:492-575`) and the marker at
  the inset position (`577-609`). The visual frame floats 0.35 m inside the
  room.

- **Duck detection compares an id to a label.**
  `e.id === waypoints[segIdx]?.label` (`ForensicSandboxPlayer.tsx:313`) will
  usually be false; only label matches work. It also only handles `enter`, not
  an exit.

- **Selected object matching is by `name`**
  (`ForensicSandboxPlayer.tsx:982`), so duplicate fixture labels select
  multiple/none.

- **No error boundary for malformed cached data.**
  Old layout rows missing `pos` will crash the 3D tree.

- **20fps `setInterval` state loop.**
  `ForensicSandboxPlayer.tsx:789-803` with O(n) recomputation per tick; no
  `requestAnimationFrame`, no pause-on-hidden, no cleanup of cursor on unmount.

- **No accessibility/keyboard controls.**
  The 3D canvas relies on mouse/touch.

- **No legend.**
  No legend for door/key location/fixture/disturbed/inferred.

- **No annotation/report-a-problem flow.**
  A user cannot flag a wrong layout or scenario.

- **No export of the visible scenario.**
  No PDF/PNG/HTML export with provenance.

---

# P1 — LLM robustness, security, legal

- **Meta ignores `max_tokens`** (`llm_client.py:68-91`).

- **No model version, seed, temperature, prompt hash stored.**
  No reproducibility.

- **Provider fallback changes results silently.**
  `provider` is stored but not shown; the report says which provider, but the
  sandbox UI does not (`sandbox.py:700`, `736-762`).

- **Catch-all fallback in the interview masks real failures.**
  `generate_socratic_interview` catches `Exception` and returns generic
  boilerplate (`sandbox.py:795-808`), so an API outage or programming bug looks
  like a successful evidence-grounded interview.

- **No JSON schema validation/repair/retry.**
  `chat_json` handles fences and trailing junk only (`llm_client.py:281-302`);
  leading prose, truncated output, wrong types, and missing keys pass through
  or cause 500s.

- **No output size limits.**
  Facts/narratives/steps have only some string truncation; a provider can return
  a huge payload.

- **Prompt injection from evidence and officer text** — P1 scenario.

- **Full evidence to third-party providers with no disclosure/redaction** —
  P0-12f.

- **No PII handling/retention policy.**
  Prompts and cached scenario payloads.

- **No audit of interview requests.**
  Only synthesis is audited, with a hardcoded role.

- **No rate limit/cost control per user or case on sandbox endpoints.**

- **Errors leak internals.**
  `HTTPException(500, str(e))` (`api.py:553-554`, `565-566`, `578-579`).

---

# P2 — Minor correctness and polish

- `_validate_layout` allows `color_hex` to be any string; invalid colours
  render unpredictably.
- `label`/`significance`/`notes` truncation is silent.
- `float(... or default)` treats `0` as missing (e.g. a legitimate `0.0`
  becomes `0.5`/`10`).
- `round(..., 2)` positions can still produce overlapping objects.
- Multiple doors on the same wall can overlap; `WallWithApertures` merges gaps
  via `cursor = max(...)` but still renders every jamb/lintel
  (`ForensicSandboxPlayer.tsx:504-572`).
- `thresholdSize`/`lintelSize` use unclamped `d.widthM` while the gap uses
  clamped `halfW` (`ForensicSandboxPlayer.tsx:507`, `540-546`), so
  thresholds/lintels can stick past a short wall.
- `EntryPointMarker` uses unclamped `ep.width_m` for jambs
  (`ForensicSandboxPlayer.tsx:596-603`).
- `gridHelper` at y=0.001 may z-fight with the floor.
- The camera can orbit below/outside walls; no wall transparency/culling.
- The right panel shows the hypothesis summary as the “Current Action”
  narrative when a frame has no narrative
  (`ForensicSandboxPlayer.tsx:302`), which reads as if it happened at that step.
- Badge parsing `scen.badge.split(" ")[0]` assumes the emoji is the first token
  (`ForensicSandboxPlayer.tsx:887`).
- `activeScenarioIdx` can point out of range after regeneration/custom insert;
  tabs highlight nothing but `currentScenario` falls back to index 0
  (`ForensicSandboxPlayer.tsx:778`).
- `handleSynthesizeScenario` closes the modal even if the parent returns no
  scenario object (`ForensicSandboxPlayer.tsx:828-843`;
  `page.tsx:227-231`).
- `synthesizeError` is not cleared when reopening the modal.
- `manualZoom` uses `Date.now()` as an id; two clicks in the same millisecond
  can be ignored.
- `onPointerOut` may not fire on touch; cursor can stick.
- No loading skeleton/error state in the 3D canvas.
- `evidence_fit_pct` DB default is 75 (`db.py:181`), which can make an
  unscored/old row look strong.
- `scenario_type` is a free string; no enum/constraint.
- `badge` includes emoji; ensure the MySQL connection charset is `utf8mb4` (not
  set in `db.py:27-36`).
- `audit_events` has no FK to cases; deleting a case deletes its audit rows
  (`api.py:200-206`), which is itself a chain-of-custody/retention issue for
  court.
- `reset_db()`/`delete_case` enumerate tables manually; easy to forget a future
  table.
- No logging of sandbox generation inputs/outputs or errors; only audit counts.
- No health/readiness check that the LLM and DB are available before showing
  the player.

---

# Testing gaps

- `backend/tests/test_pipeline.py` never exercises
  `backend/pipeline/sandbox.py`.
- No unit tests for `_validate_layout`, `_resolve_steps_to_trajectory`,
  `_avoid_fixture_collisions`, `calculate_physics_validation`,
  `_persist_scenarios`, or `_row_to_scenario`.
- No property tests for segment/wall/fixture non-intersection.
- No golden tests for timing, clock, or milestone selection.
- No migration test (old schema → new schema).
- No concurrency test for simultaneous generation.
- No frontend tests for the player, timeline, selection, or camera.
- No test for empty evidence, untimed observations, malformed LLM output, or
  long case IDs.

---

# What “real-world perfect” requires

1. **A real scene graph, not one rectangle.**
   Rooms, internal walls/doors, multiple floors, outdoor areas, vehicles; nodes
   belong to spaces; entry points can be internal or external.

2. **Explicit provenance and uncertainty on every element.**
   `{kind: observed|reported|inferred|defaulted, refs: [observation_id +
   source_locator + quote], confidence, rationale}`. Reject or visually mark
   anything with no refs. Never fabricate a default door/size without flagging
   it as a default.

3. **A serialisable time model with separate `depart`, `transit`, `arrive`,
   `dwell`, and `evidence_time`.**
   Actions occur during dwell at the correct node; milestones map to arrival
   intervals; total duration is consistent across backend and frontend.

4. **Evidence-anchored timestamps.**
   Store source clocks and offsets (CCTV +5m32s, alarm, witness wristwatch),
   anchor each evidence-linked step to a real timestamp where possible, and
   clearly mark estimated vs. anchored times. Include date/timezone.

5. **A deterministic navigation/collision layer.**
   Navmesh or grid A*, swept capsule vs. walls/AABBs, wall apertures with
   width/height, iterative detours, final validation of the **rendered** path,
   door state, reachability, and action-specific speed/acceleration.

6. **A deterministic evidence-fit rubric.**
   Count validated supporting citations, contradicted claims, physics
   violations, evidence coverage, and missing facts; combine with the LLM’s
   qualitative score; sort after validation; show raw and capped scores and why.

7. **Per-step citations.**
   Every frame/narrative line carries `evidence_refs` with source locators;
   bracket citations are resolved and verified, not free text.

8. **A clickable route and provenance UI.**
   Render the path as segments, colour auto-inserted vs. evidence-backed hops,
   let the user click any segment/object and see the exact observation, source
   file, page/frame, and inference rationale.

9. **Multi-actor support.**
   Suspects/accomplices/victims/witnesses/cameras as first-class entities with
   positions, paths, and evidence refs.

10. **Immutable, versioned artefacts.**
    Evidence fingerprint, schema version, prompt version, model, provider,
    generation time, content hash; never delete prior scenario versions; audit
    every generation/regeneration with the real user.

11. **A human correction loop.**
    Officers can correct the layout/fixtures/doors and annotate “inferred” vs.
    “fact,” with audit and re-generation against the corrected scene.

12. **A proper API.**
    POST/background generation, read-only GETs, RBAC (`view_case`,
    `generate_scenario`), rate limits, error taxonomy, job progress/cancel.

13. **An exportable court pack.**
    Layout + provenance + citations + physics report + version history + hashes,
    in a format a defence lawyer can inspect.

14. **A test suite for universal cases.**
    Synthetic cases with no timeline, many doors, internal rooms, blocking
    fixtures, multi-actor, thin evidence, malformed LLM output, old cache
    schemas, and concurrent generation; property tests that the final rendered
    path never intersects a wall or fixture.

---

# Recommended remediation order

1. **P0-1 migration** — otherwise existing installs are broken.
2. **P0-2 / P0-6 wall and fixture collision** — make the final rendered path
   valid; otherwise every scenario is suspect.
3. **P0-3 time/action model** — separate transit and dwell; fix milestones and
   clock.
4. **P0-4 / P0-5 provenance and path audit** — enforce refs, resolve citations,
   render/click path, surface auto-inserted.
5. **P0-7 scoring/ranking** — deterministic rubric, contradiction penalty, sort,
   show capped score.
6. **P0-9 evidence time anchoring** — source clocks, actual timestamps,
   duration windows.
7. **P0-11 / P0-12 cache/audit versioning** — evidence hash, immutable versions,
   user attribution, provider/model disclosure.
8. **P0-8 / P0-10 model/API** — multi-space/multi-actor data model; POST
   generation, RBAC, rate limit, error/empty states.
9. Then P1/P2 polish and tests.

---

# Appendix A — claims vs. reality

| Claim | Reality |
|---|---|
| “Every exterior<->interior transition is auto-routed … provably wall-safe by construction” (`sandbox.py:560-568`) | Exterior spawn is fixed south; exterior↔door leg skips collision; no segment-vs-wall test. |
| “Click any wall or object to see the exact evidence” (`ForensicSandboxPlayer.tsx:988-990`) | Walls have no click handler; path segments are not rendered. |
| “Optical line-of-sight checks” (`page.tsx:1146`) | No line-of-sight/occlusion implementation; only an interview question label. |
| “Top 3 evidence-fit-ranked” (`sandbox.py:386-420`) | No sorting; badge is positional; contradictions do not affect score. |
| “Every auto-inserted routing/detour hop is flagged” (`sandbox.py:566-568`) | Flagged on frames but never rendered; not in `node_sequence`/trajectory; not persisted. |
| “Real start_clock from evidence” (`ForensicSandboxPlayer.tsx:98`) | Only an earliest-string anchor; intermediate times are LLM `dt_sec`, not evidence times. |
| “Nothing drawn that isn’t traceable; evidence_refs on every node” | Empty refs accepted; default door/size fabricated; untimed observations invisible; citation validation is existence-only. |
| “Deterministic physics caps confidence” | Physics checks points only; detour is not revalidated; score cap is applied but original score is lost. |
| “Officer custom hypothesis with Socratic interview” (`sandbox.py:769-808`) | Three fixed multiple-choice questions; questions not persisted/sent; answers only. |
| “Persistence, reloadable, regenerable” | No migration, no evidence fingerprint, stale cache, `REPLACE` destroys history, concurrency races. |

---

# Appendix B — file map

| File | Role in the sandbox |
|---|---|
| `backend/pipeline/sandbox.py` | Layout prompt/validation, scenario prompt, step resolution, auto-routing, physics, persistence, custom interview, cache. |
| `backend/db.py` | Schema for `case_sandbox_layout` / `case_sandbox_scenarios`; audit chain. |
| `backend/api.py` | Sandbox endpoints (`GET /sandbox/scenarios`, custom interview/synthesis). |
| `backend/pipeline/timeline.py` | Timeline ordering; start-clock source. |
| `backend/pipeline/observe.py` | Observation time extraction; confirms untimed/“HH:MM” limitations. |
| `backend/llm_client.py` | Provider fallback, `chat_json`, meta calls. |
| `backend/auth.py` | Role permissions; sandbox endpoints do not use them. |
| `frontend/app/scene/ForensicSandboxPlayer.tsx` | 3D player, timing, milestone navigation, interview/custom UI, physics panel. |
| `frontend/app/case/[caseId]/page.tsx` | Sandbox loading, `Promise.all`, error swallowing, custom scenario insert, copy. |
| `frontend/app/lib/api.ts` | Sandbox API client (no timeout/abort). |
| `Sample test case/` | Real example with “secured internal dispensary,” NVR +5m32s offset, and internal geometry the model cannot represent. |
| `backend/tests/test_pipeline.py` | Does not test sandbox. |
