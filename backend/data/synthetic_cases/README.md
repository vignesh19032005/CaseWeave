# Synthetic demonstration cases

Every case here is **entirely fictional**: invented people, companies, places, vehicles and times, written for testing and for the demo.
No real case, person or record is used, so there is nothing to redact and no legal exposure from real investigations.

Each folder holds evidence files of different types (text logs, JSON logs, statements, an examiner's scene report, a diagram) and a
`ground_truth.json` that lists the contradictions that were **planted on purpose**. The benchmark (`scripts/sandbox_benchmark.py`) measures
how many of them the system finds. The diagrams are drawn by `make_diagrams.py`, they are illustrations and not photographs.

| Folder | Kind | Evidence types |
|---|---|---|
| burglary_warehouse | Night burglary through a side window | alarm-panel log (JSON), door-access JSON, CCTV log, two statements, examiner's scene report, floor diagram |
| road_accident_junction | Two-vehicle collision at a signalled junction | vehicle telematics JSON, signal-phase log (JSON), dashcam transcript, three statements, scene measurements, junction diagram |
| indoor_assault_office | Assault in a storeroom of a small office | emergency-call transcript, access-control log (JSON), corridor CCTV log, medical note, three statements, floor diagram |
