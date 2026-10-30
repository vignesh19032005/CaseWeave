# Master Prompt — Dataset & Resource Search for CaseWeave AI

Copy-paste the block below into any search tool / AI assistant / research agent when hunting for datasets, corpora, or reference material for this project.

---

## MASTER PROMPT

```
I'm building CaseWeave AI — an AI-powered investigation workspace that connects
CCTV footage, photos, witness statements, forensic reports, and legal documents
into a single evidence-linked case file. It detects cross-source contradictions,
builds an evidence-linked 3D scene, and retrieves relevant law for case facts.
Built for a Meta AI hackathon (10-day build), with an eventual goal of being
presented as a credible proof-of-concept to a real police department (Tamil
Nadu / India context) for a possible future pilot.

I need you to find datasets, corpora, or reference resources for the following
sub-needs. For EVERY result, report: (1) exact license/terms, (2) whether it
permits redistribution/public demo use vs research-only, (3) whether it
contains real personal/case data vs synthetic/simulated data, (4) direct
source link.

SUB-NEEDS TO SEARCH FOR:

1. Surveillance/CCTV-style video datasets (any domain: retail, warehouse,
   street, indoor) — for testing frame extraction + object/event detection.
   Open-vocabulary content preferred over narrow "crime-only" footage.

2. Forensic / crime-scene imagery or 3D scene datasets — for testing scene
   reconstruction and evidence-object placement pipelines.

3. Witness-statement-style or incident-report-style text corpora (any
   domain — insurance claims, accident reports, etc. are fine substitutes)
   — for testing text extraction, classification (observed/reported/
   inferred), and cross-source comparison.

4. Indian legal corpora: court judgments, statutes, especially anything
   touching electronic evidence admissibility (BSA 2023 Section 63 /
   IT Act Section 65B equivalents) — for legal RAG retrieval testing.
   Prefer official/government sources (SCR portal, India Code, eCourts/
   AWS Open Data) over scraped third-party mirrors.

5. Single-image-to-3D-object benchmark datasets — for evaluating SAM 3D
   Objects / TripoSR / Hunyuan3D-2 reconstruction quality on everyday
   objects (bags, vehicles, furniture, tools).

6. Audio datasets with transcripts (any domain) — for testing ASR
   pipelines (MMS / Whisper-class models) before touching anything
   sensitive.

7. Any existing open-source repos or published benchmarks for: cross-
   document contradiction/conflict detection, evidence chain-of-custody
   logging, or AI-assisted investigation tooling — to check for prior art
   and reusable evaluation methodology (not to copy code wholesale,
   to avoid reinventing evaluation metrics).

For each category, rank results by: license permissiveness first, realism/
relevance second, size/quality third. Flag clearly if NOTHING suitable
exists and synthetic self-generation is the only safe option.
```

---

## Hard constraints (never relax these)

- **No real case data, ever, without explicit written department authorization + anonymization clearance.** Scraping or sourcing actual police case files, real victim/suspect identities, or real CCTV footage from an actual incident is off-limits for this project at hackathon/demo stage, full stop.
- **No dataset with unclear or "Other" license used in any public demo** (e.g. don't put UCF-Crime clips on stage even though research use of the dataset itself is common — the license ambiguity on redistribution is the problem, not the research use).
- **No bulk-scraping a site whose ToS doesn't clearly allow it** (e.g. don't mass-scrape IndianKanoon directly — use eCourts/AWS Open Data or hand-picked SCR portal judgments instead).
- **No real PII** (names, phone numbers, ID numbers, faces of real identifiable people) in anything that goes into a demo, screenshot, or exported report — synthetic/fictional only.
- **Meta-only AI constraint stays separate from this dataset constraint** — datasets can come from anywhere; only the models processing them must stay Meta (see PLAN.md Model Fallback Matrix). Don't let a dataset's origin imply anything about model choice.

## Liberties (where you CAN relax, deliberately)

- **Domain substitution is fine.** A warehouse/retail CCTV dataset, an insurance-claim text corpus, or a generic accident-report dataset all exercise the same pipeline mechanics (extraction, classification, timeline, contradiction detection) as an actual crime case — you don't need crime-specific content to validate the *mechanism*. Prefer these over anything crime-labeled with murky licensing.
- **Research-only / non-commercial license datasets (e.g. CrossRow) are fine for internal dev/testing and even private team demos**, just not for the public hackathon demo, published report screenshots, or anything pitched to police as a deliverable. Label internally which tier each dataset belongs to: `demo-safe` vs `dev-only`.
- **Synthetic self-generated data is always safe and always the fallback** — staged phone footage, written fictional witness statements, fabricated access logs. When in doubt between a legally murky real dataset and writing your own synthetic equivalent, default to synthetic; it costs an afternoon, not a legal review.
- **Legal corpus is the one area where real data is both available and encouraged** — official government judgment/statute text is public domain in India. Use real judgments here; this is the one place "real data" strengthens the pitch without any of the above risk.
- **Pre-trained model benchmarks/weights have their own separate licenses from the datasets they were trained on** — don't conflate "the dataset used to train SAM 3D Objects" with "the dataset I'm allowed to test it on." You can use the model via its own license even if its training data had different terms.

## Output format to request from any search

For every dataset/resource found, require this structure back:

```
Name:
Source link:
License:
Redistribution/public-demo allowed? (yes / no / unclear — treat unclear as no)
Real personal data present? (yes / no / synthetic)
Relevant to which CaseWeave stage: (0-10, see PLAN.md)
Recommended tier: demo-safe | dev-only | reject
```
