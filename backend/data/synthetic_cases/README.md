# Synthetic demonstration cases

Every case here is **entirely fictional**: invented people, companies, places, vehicles and times, written for testing and for the demo.
No real case, person or record is used, so there is nothing to redact and no legal exposure from real investigations.

Each folder holds evidence files of different types (text logs, JSON logs, statements, an examiner's scene report, a diagram), with a few contradictions between sources written in on purpose. The diagrams are drawn by `make_diagrams.py`; they are illustrations, not photographs.

| Folder | Kind | Evidence types |
|---|---|---|
| burglary_warehouse | Night burglary through a side window | alarm-panel log (JSON), door-access JSON, CCTV log, two statements, examiner's scene report, floor diagram |
| road_accident_junction | Two-vehicle collision at a signalled junction | vehicle telematics JSON, signal-phase log (JSON), dashcam transcript, three statements, scene measurements, junction diagram |
| indoor_assault_office | Assault in a storeroom of a small office | emergency-call transcript, access-control log (JSON), corridor CCTV log, medical note, three statements, floor diagram |
| pharmacy_burglary_photos | Night burglary of a pharmacy stockroom | alarm log (JSON), CCTV log, examiner's report, two statements, four photographs (used for photo readings and object boxes) |

The road collision runs through the evidence analysis, timeline, contradictions and report. Its 3D scene is not built, because the scene builder draws the inside of buildings.
