# 3-minute demo: shot list and narration

Rules we are designing for (from the public event pages; check the official rules before submitting): 3 minutes or less, English, the video is the main judged artifact and must show only what was built during the event. Captions are burned in so it reads with the sound off.

Narration is spoken by a synthetic voice (the video says so in the last frame). Everything on screen is a **fictional** case.

| Time | On screen | Narration (about 150 words per minute) | Case |
|---|---|---|---|
| 0:00 to 0:15 | Title, then the problem number | "In 2022 Indian police had fifty-six lakh cases under investigation, and about a third were still open at year end. Contradictions between statements, logs and photos are easy to miss. CaseWeave finds them." | any |
| 0:15 to 0:45 | Case page: evidence list, conflicts panel. Click one conflict: the driver says his light was green, the signal log says red for twenty seconds | "Here is a fictional collision. The driver says the light was green. The signal controller's log says red for twenty seconds before the impact. The tool flags it and points at both sources, so a person can check." | road accident |
| 0:45 to 1:30 | 3D scene of the office assault: rooms, people walking, view cones turning red, "seen" label. Then the pharmacy case photos with boxes and "Photo readings (inferred)" | "From the evidence, CaseWeave builds a walkable scene and several different accounts of what happened. Cones show who could see whom. Meta's vision model reads the photos, SAM draws boxes on them, and everything it infers is marked inferred." | assault, then pharmacy |
| 1:30 to 2:05 | Architecture slide, then a scenario flagged for walking through a wall, then the repair: "Repaired by a Meta model that called the checker as a tool" | "The model proposes. Code decides. A Meta model never emits coordinates and never says what is possible. It calls our checker as a tool, fixes the plan, and we keep whichever version the checker prefers." | burglary |
| 2:05 to 2:35 | Benchmarks table, then side-by-side Meta-only vs local Llama | "We measured it on three fictional cases with planted contradictions. Here is how many we found, how many faults the checker caught, and how Meta's models compare with a local Llama that never leaves the building." | all three |
| 2:35 to 2:55 | Limits slide | "A scenario is a possibility, not a finding. The reviewer is an opinion. Only fictional cases have been run, and the next step is validation with real investigators." | n/a |
| 2:55 to 3:00 | Repo link, "Narrated by a synthetic voice" | "CaseWeave. The model proposes, the code decides." | n/a |

Rules for recording: dark theme, 1920x1080, browser zoom 100 to 110 percent, no real data, no credentials or terminal windows in frame, pre-generated everything, one backup recording of the full flow.
