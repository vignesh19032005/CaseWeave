# Master Prompt — Full Synthetic Case Generation (Text Evidence Only)

**Scope note:** this prompt generates every TEXT-based evidence artifact end-to-end, plus ground truth for evaluation. It does NOT generate photos or video — those stay real, staged, consenting-actor footage (see earlier guidance). Feed this to GPT/Llama/Muse Spark/Claude — any capable LLM can execute it; swap in your Meta model for the actual hackathon build per the Model Fallback Matrix in PLAN.md.

---

## MASTER PROMPT

```
Generate 2 complete fictional investigation cases for a demo of CaseWeave AI,
an evidence-linking and contradiction-detection system. Everything you produce
is 100% fictional — no real people, no real places, no real incidents. Use
clearly invented names, addresses, and case numbers (e.g. "Case CW-001",
never a real FIR number format tied to an actual jurisdiction's real
numbering in a way that could be mistaken for genuine).

CASE 1 — "Warehouse Incident" (property theft, discrepancy = clock mismatch)
CASE 2 — "Office Break-in" (unauthorized access, discrepancy = conflicting
witness descriptions)

For EACH case, produce ALL of the following, as separate clearly labeled
sections, in valid JSON where specified:

1. CASE OVERVIEW
   - case_id, title, fictional location, fictional date/time range,
     one-paragraph summary of what allegedly happened.

2. EVIDENCE INVENTORY (list every item, including the ones that will be
   real photos/video you'll shoot separately — mark those as
   "type": "video" or "type": "photo" with a text DESCRIPTION of what
   the clip/photo should show, so I know what to film. Everything else
   (statements, logs, reports) must be the actual full text content.)

3. WITNESS STATEMENTS (write 2-4 full fictional statements per case,
   1-2 paragraphs each, first-person, with a natural amount of
   imprecision — approximate times, hedging language like "around" or
   "I think". Deliberately make ONE statement conflict with another
   piece of evidence in a specific, identifiable way.)

4. ACCESS LOG / SENSOR LOG (structured fictional log — JSON array of
   {timestamp, event, location, device_id} — covering the incident
   window, with ONE entry deliberately time-shifted to create the
   planted discrepancy.)

5. INCIDENT REPORT (1-2 page fictional formal report, written as an
   investigating officer would, referencing the evidence above by
   item number.)

6. FORENSIC REPORT EXCERPT (short fictional forensic note, e.g. object
   condition, fingerprint note, or damage assessment — 1 paragraph,
   with an explicitly stated limitation, e.g. "latent print insufficient
   for comparison".)

7. GROUND TRUTH ANNOTATION (JSON — this is the answer key, used to
   evaluate whether CaseWeave's AI stages work correctly):
   {
     "expected_observations": [ {description, source_item, classification: observed|reported|inferred|disputed|unknown} ... ],
     "expected_timeline_events": [ {time_or_range, description, source_item} ... ],
     "planted_discrepancy": {
       "claim_a": "", "source_a": "",
       "claim_b": "", "source_b": "",
       "nature_of_conflict": "",
       "correct_resolution_hint": ""
     },
     "expected_scenarios": [ {name, assumption, supporting_evidence, challenging_evidence} ... ],
     "missing_evidence_flags": [ "" ]
   }

8. LEGAL QUESTION FOR RAG TESTING (one realistic natural-language legal
   question an investigator would ask about THIS case's facts — e.g.
   about electronic evidence admissibility — that I will separately
   test against a real curated Indian legal corpus. Do not invent legal
   citations here; just write the question.)

9. FILMING BRIEF (plain-language instructions for the 3 video clips and
   5 photos this case needs: what each should show, roughly how long,
   what props/location type fits the case overview, so the output is
   consistent with the text evidence you generated.)

Constraints while generating:
- Every claim must be traceable to a specific invented source item
  (no floating unattributed facts).
- Include realistic imperfection: approximate times, hedge words,
  at least one piece of explicitly missing evidence noted in the
  incident report.
- Classification labels (observed/reported/inferred/disputed/unknown)
  must be used consistently with CaseWeave's schema, not invented terms.
- Output everything in one response, clearly delimited by the section
  headers above, case by case.
```

---

## Why this covers "can GPT plan+generate all" — with the one carve-out

- **Text artifacts (sections 1,2 text parts,3,4,5,6,7,8): yes, fully AI-generatable, this prompt does all of it in one shot**, for both cases. This is the correct and recommended use of AI generation — zero legal/realism risk, saves a day of manual writing.
- **Section 9 (filming brief) is AI-generated too** — but its *output* (the actual video/photo pixels) still has to come from you with a real phone, for the reasons already covered: realism for 3D reconstruction, and no confirmed Meta image/video-generation model to stay compliant with the hackathon's Meta-only rule.
- **Ground truth (section 7) is the part that makes this worth doing properly** — without it you can't score whether Stage 2 (observations) or Stage 4 (discrepancy detection) actually got the right answer. Generate it up front, before you build the detection pipeline, not after.

## How to use the output

1. Run this prompt once (any capable LLM, doesn't need to be Meta-only for this generation step — it's dataset creation, not the product pipeline itself).
2. Save each case's JSON/text sections into your `EvidenceItem`/`Observation` seed data.
3. Follow the filming brief (section 9) to shoot the 3 clips + 5 photos per case with a phone — **recommended**, see risk note below if using AI image/video gen instead.
4. Keep the ground truth (section 7) separate and hidden from the pipeline — it's your answer key, not an input.

---

## AI-generated photo/video prompts (use with caution — see risk note)

**Risk note, read before using these:** AI-generated images/video introduce geometry/lighting artifacts that measurably hurt SAM 3D Objects reconstruction quality — the exact pipeline stage you're trying to showcase. There is also no confirmed Meta text-to-image or text-to-video API, so generating these forces a non-Meta model (Midjourney/DALL-E/Stable Diffusion/Sora/Runway/etc.), which breaks the hackathon's Meta-only constraint if used in the actual submission. Treat these as **dev-placeholder / background-filler only** — swap in real staged phone footage before the final demo, at minimum for anything that touches SAM 3D Objects reconstruction.

### Photo generation prompts (per case, run once per evidence photo needed)

```
Generate a photorealistic image, security-camera-adjacent still photo style,
of [OBJECT] on a plain concrete warehouse floor, single object, centered,
even overhead lighting, no people, no text/logos, no watermarks, neutral
unbranded object, slight wear/scuff detail for realism, straight-on angle
suitable for 3D shape reconstruction (avoid extreme foreshortening or
motion blur). Background: plain wall or empty shelving, out of focus.
```
Fill `[OBJECT]` from the case's evidence inventory (e.g. "a medium cardboard shipping box with one torn flap," "a dark backpack lying on its side," "a metal toolbox with a dented corner").

Repeat per object, 2-3 angle variants each (front, 3/4 angle, side) if the tool supports multi-angle generation — single-image-to-3D models do better with a clean single canonical view, so don't over-rotate.

### Video generation prompts (per case, one per clip in the filming brief)

```
Generate a short (15-20 second) static-camera surveillance-style video clip,
fixed high-angle wide shot, no camera movement or zoom, slightly
desaturated color grade typical of CCTV footage, timestamp overlay in
corner reading "[FAKE TIMESTAMP]" in a basic monospace font. Scene: a
[LOCATION TYPE, e.g. "warehouse entrance with a metal roller door"].
Action: [ACTION, e.g. "a person in dark clothing enters through the door,
walks to a stack of boxes, picks one up, and exits frame left"]. No
audio needed. No real faces/identifiable likeness — keep the person
featureless/silhouetted or stylized, not photoreal, to avoid implying
a real individual.
```
Fill `[FAKE TIMESTAMP]`, `[LOCATION TYPE]`, `[ACTION]` straight from the case's filming brief (section 9) output.

**Specific extra caution on video:** even "no real faces" AI-generated people can accidentally resemble real individuals (known failure mode of generative video models). Prefer silhouette/low-detail rendering, or just do the real phone recording — it's faster than iterating a video-gen prompt to get something usable anyway, and has none of these problems.
