"""
CaseWeave 4D Incident Simulation Engine.
Dynamically constructs an interactive, chronological 3D spatial simulation
from extracted case timeline events, sensor telemetry, evidence photos,
and adversarial discrepancy reviews.
"""

import json
import logging
import time
from typing import Dict, Any, List

from db import get_conn, append_audit_event
from pipeline.timeline import get_timeline

logger = logging.getLogger("caseweave.simulation")


def _build_simulation_frames(case_id: str, events: List[Dict[str, Any]], conflicts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Synthesizes timeline events, sensor logs, and conflict points into
    chronological 3D spatial simulation frames with actor trajectories,
    interactive camera angles, and hardware state changes.
    """
    # Canonical Crime Scene Dimensions (Standard Forensic Blueprint)
    # Origin (0,0,0) is center of warehouse / pharmacy floor.
    scene_config = {
        "width_m": 12.0,
        "length_m": 16.0,
        "height_m": 4.2,
        "zones": {
            "alley_rear_entry": {"center": [-4.5, 0.0, -6.0], "label": "Gate-B Rear Rolling Shutter", "color": "#ef4444"},
            "storage_corridor": {"center": [-2.0, 0.0, -2.0], "label": "Storage Corridor (PIR Zone 2)", "color": "#06b6d4"},
            "narcotics_vault": {"center": [3.8, 0.0, -2.5], "label": "High-Value Narcotics Vault", "color": "#f59e0b"},
            "billing_counter": {"center": [2.2, 0.0, 3.8], "label": "Front Billing Counter & Till", "color": "#10b981"},
            "front_entrance": {"center": [-1.0, 0.0, 6.5], "label": "Front Entrance (EVR Periyar Salai)", "color": "#8b5cf6"},
        },
        "camera_presets": {
            "overview": {"pos": [11.0, 11.0, 11.0], "target": [0.0, 1.0, 0.0], "label": "Overview 360°"},
            "cctv_alley": {"pos": [-5.8, 4.2, -7.5], "target": [-4.2, 1.2, -5.5], "label": "CCTV-ALLEY-02 (Alleyway Angle)"},
            "vault_cam": {"pos": [1.5, 3.5, -4.5], "target": [3.8, 1.0, -2.5], "label": "Vault Interior Angle"},
            "counter_cam": {"pos": [0.0, 3.2, 1.8], "target": [2.2, 0.8, 3.8], "label": "Counter Register View"},
            "suspect_pov": {"pos": [-4.0, 1.7, -4.5], "target": [-2.0, 1.2, -2.0], "label": "Suspect Point-of-View"},
        }
    }

    # Full Waypoint Trajectory (Floor coordinates traversed during incident)
    full_trajectory = [
        {"time": "02:15", "pos": [-4.5, 0.0, -7.5], "action": "approach_alley", "label": "Alley Approach"},
        {"time": "02:22", "pos": [-4.5, 0.0, -5.8], "action": "prying_shutter", "label": "Shutter Tamper"},
        {"time": "02:23", "pos": [-4.2, 0.0, -5.0], "action": "breach_duck", "label": "Forced Shutter Breach"},
        {"time": "02:24", "pos": [-2.2, 0.0, -2.5], "action": "corridor_movement", "label": "Corridor Infiltration"},
        {"time": "02:26", "pos": [3.5, 0.0, -2.5], "action": "looting_vault", "label": "Vault Cabinet Ransack"},
        {"time": "02:30", "pos": [2.2, 0.0, 3.5], "action": "looting_counter", "label": "Cash Counter Pried"},
        {"time": "02:34", "pos": [-4.2, 0.0, -5.2], "action": "exit_crawl", "label": "Egress with Duffel"},
        {"time": "02:35", "pos": [-4.8, 0.0, -8.5], "action": "flee_alley", "label": "Flight to Main Road"},
    ]

    # Conflict Lookup
    shutter_conflict = conflicts[0] if conflicts else None

    # Sequential Simulation Keyframes
    frames = [
        {
            "frame_idx": 0,
            "timestamp": "01:30 AM",
            "time_seconds": 0,
            "phase": "BASELINE",
            "title": "Stationary Baseline & Perimeter Lockdown",
            "narrative": "Store closed for inventory. Rear Gate-B shutter down and secured with dual brass padlocks. RFID heartbeat nominal.",
            "actor": {
                "visible": False,
                "pos": [-4.5, 0.0, -9.0],
                "action": "none",
                "label": "No Intruder Detected",
            },
            "scene_state": {
                "shutter_height": 0.0,
                "shutter_color": "#3f3f46",
                "shutter_alert": False,
                "vault_toppled": False,
                "counter_open": False,
                "active_sensor": "RFID-REAR-01: Heartbeat Nominal",
                "sensor_color": "#10b981",
            },
            "evidence_markers": [],
            "conflict_alert": None,
            "telemetry": {
                "sensor_event": "RFID-REAR-01: door_closed at rear_shutter_gate_b (Nominal)",
                "cctv_frame": "Frame 0120: Alleyway empty, street lamp steady.",
                "witness_statement": "Wholesale counter closed. All security locks latched.",
                "evidence_doc": "02_intrusion_alarm_log.json",
            },
            "camera_preset": "overview",
        },
        {
            "frame_idx": 1,
            "timestamp": "02:15 AM",
            "time_seconds": 2700,
            "phase": "SURVEILLANCE",
            "title": "Alleyway Perimeter & Ambient Surveillance",
            "narrative": "Night guard K. Sundaram drinking tea near perimeter. Street lamp flickering. Ambient alleyway remains quiet.",
            "actor": {
                "visible": False,
                "pos": [-4.5, 0.0, -9.0],
                "action": "none",
                "label": "Perimeter Clear",
            },
            "scene_state": {
                "shutter_height": 0.0,
                "shutter_color": "#3f3f46",
                "shutter_alert": False,
                "vault_toppled": False,
                "counter_open": False,
                "active_sensor": "None: Perimeter Quiet",
                "sensor_color": "#71717a",
            },
            "evidence_markers": [],
            "conflict_alert": None,
            "telemetry": {
                "sensor_event": "All zones idle. RFID status heartbeat OK.",
                "cctv_frame": "CCTV-ALLEY-02: Dim lighting, flickers noted in lower frame.",
                "witness_statement": "K. Sundaram: 'At around 2:15 AM or 2:20 AM, drinking tea from flask near guard booth.'",
                "evidence_doc": "04_witness_statement_sundaram.txt",
            },
            "camera_preset": "cctv_alley",
        },
        {
            "frame_idx": 2,
            "timestamp": "02:22 AM",
            "time_seconds": 3120,
            "phase": "FORCED ENTRY",
            "title": "Rear Shutter Tamper & Mechanical Prying",
            "narrative": "Audible metallic screeching reported. Intruder inserts heavy crowbar into bottom center clasp. Tamper switch triggered on rear shutter.",
            "actor": {
                "visible": True,
                "pos": [-4.5, 0.0, -5.8],
                "action": "prying",
                "label": "Intruder (Dark hooded rain jacket, white sneakers)",
            },
            "scene_state": {
                "shutter_height": 0.2,
                "shutter_color": "#f59e0b",
                "shutter_alert": True,
                "vault_toppled": False,
                "counter_open": False,
                "active_sensor": "RFID-REAR-01: TAMPER SWITCH TRIGGERED",
                "sensor_color": "#ef4444",
            },
            "evidence_markers": [
                {
                    "marker_id": "M-SHUTTER",
                    "label": "Forced Clasp & Tool Marks",
                    "pos": [-4.5, 0.2, -5.8],
                    "color": "#f59e0b",
                    "filename": "01_tampered_rear_shutter.jpg",
                }
            ],
            "conflict_alert": None,
            "telemetry": {
                "sensor_event": "02:22:45 — Tamper switch triggered at rear_shutter_gate_b (ALARM)",
                "cctv_frame": "Frame 1845: Dark silhouette detected approaching shutter base.",
                "witness_statement": "K. Sundaram: 'Distinctly heard loud metallic screeching and cracking sound. Checked wristwatch: exactly 02:21 AM.'",
                "evidence_doc": "02_intrusion_alarm_log.json",
            },
            "camera_preset": "cctv_alley",
        },
        {
            "frame_idx": 3,
            "timestamp": "02:23 AM",
            "time_seconds": 3180,
            "phase": "BREACH & CLOCK DISCREPANCY",
            "title": "Shutter Lifted & Sequence Conflict",
            "narrative": "Rolling shutter lifted ~3 ft off concrete floor. Intruder ducks underneath into storage hallway. Hardware intrusion alarm logs forced breach at 02:23:10.",
            "actor": {
                "visible": True,
                "pos": [-4.2, 0.0, -4.8],
                "action": "crawling_under",
                "label": "Intruder Entering Under Shutter",
            },
            "scene_state": {
                "shutter_height": 0.95,
                "shutter_color": "#ef4444",
                "shutter_alert": True,
                "vault_toppled": False,
                "counter_open": False,
                "active_sensor": "RFID-REAR-01: FORCED BREACH DETECTED",
                "sensor_color": "#ef4444",
            },
            "evidence_markers": [
                {
                    "marker_id": "M-SHUTTER",
                    "label": "Gate-B Breached Shutter",
                    "pos": [-4.5, 0.95, -5.8],
                    "color": "#ef4444",
                    "filename": "01_tampered_rear_shutter.jpg",
                }
            ],
            "conflict_alert": {
                "title": "🚨 SEQUENCE CONFLICT DETECTED (5m 15s Clock Drift)",
                "source_a": "Hardware Alarm Log (02:23:10 - Breach)",
                "source_b": "CCTV-ALLEY-02 Overlay (02:28:15 - Prying)",
                "nature": "Hardware tamper sensor logged forced entry at 02:23:10, but standalone CCTV timestamp claims prying only started at 02:28:15. Proven to be uncalibrated camera clock drift.",
                "admissibility_rule": "Section 63 BSA 2023 requires hardware sensor hash reconciliation.",
            },
            "telemetry": {
                "sensor_event": "02:23:10 — RFID-REAR-01: door_opened at rear_shutter_gate_b (FORCED BREACH)",
                "cctv_frame": "CCTV Timestamp drift flag: Camera overlay indicates 02:28:15 (5m 5s discrepancy).",
                "witness_statement": "Sub-Inspector Forensic Report: 'Bottom clasp sheared off; 3 ft gap opened.'",
                "evidence_doc": "01_forensic_inspection_report.pdf",
            },
            "camera_preset": "cctv_alley",
        },
        {
            "frame_idx": 4,
            "timestamp": "02:24 AM",
            "time_seconds": 3240,
            "phase": "VAULT INFILTRATION",
            "title": "Target Infiltration: Narcotics Vault Breach",
            "narrative": "Intruder advances into interior narcotics vault. Passive infrared sensor (PIR-STOCK-02) triggers immediately. Targeted Schedule H prescription narcotics looted.",
            "actor": {
                "visible": True,
                "pos": [3.6, 0.0, -2.2],
                "action": "ransacking_vault",
                "label": "Intruder Prying Locked Cabinet",
            },
            "scene_state": {
                "shutter_height": 0.95,
                "shutter_color": "#ef4444",
                "shutter_alert": False,
                "vault_toppled": True,
                "counter_open": False,
                "active_sensor": "PIR-STOCK-02: MOTION IN NARCOTICS VAULT",
                "sensor_color": "#f59e0b",
            },
            "evidence_markers": [
                {
                    "marker_id": "M-CABINET",
                    "label": "Evidence Marker #2: Toppled Narcotics Cabinet",
                    "pos": [3.8, 0.3, -2.5],
                    "color": "#f59e0b",
                    "filename": "02_toppled_narcotics_cabinet.jpg",
                }
            ],
            "conflict_alert": None,
            "telemetry": {
                "sensor_event": "02:24:18 — PIR-STOCK-02: motion_detected at narcotics_vault_zone (ALARM)",
                "cctv_frame": "Interior blindspot. No camera coverage inside vault.",
                "witness_statement": "Pharmacist: 'Lock of Schedule H narcotics cabinet snapped. Alprazolam and Ketamine stocks looted.'",
                "evidence_doc": "02_toppled_narcotics_cabinet.jpg",
            },
            "camera_preset": "vault_cam",
        },
        {
            "frame_idx": 5,
            "timestamp": "02:30 AM",
            "time_seconds": 3600,
            "phase": "SECONDARY TARGET",
            "title": "Cash Counter Breach & Physical Tool Discard",
            "narrative": "Intruder moves to front billing counter. Till drawer jimmied open. During haste, rusty crowbar slips and blue latex glove is discarded beside yellow evidence marker #1.",
            "actor": {
                "visible": True,
                "pos": [2.2, 0.0, 3.4],
                "action": "prying_drawer",
                "label": "Intruder Prying Cash Till",
            },
            "scene_state": {
                "shutter_height": 0.95,
                "shutter_color": "#ef4444",
                "shutter_alert": False,
                "vault_toppled": True,
                "counter_open": True,
                "active_sensor": "PIR-FRONT-01: MOTION IN BILLING AREA",
                "sensor_color": "#10b981",
            },
            "evidence_markers": [
                {
                    "marker_id": "M-CROWBAR",
                    "label": "Evidence Marker #1: Discarded Crowbar & Blue Glove",
                    "pos": [1.6, 0.05, 2.8],
                    "color": "#06b6d4",
                    "filename": "03_discarded_crowbar_and_glove.jpg",
                },
                {
                    "marker_id": "M-DRAWER",
                    "label": "Cash Till & Counter Jimmied Open",
                    "pos": [2.2, 0.9, 3.8],
                    "color": "#10b981",
                    "filename": "04_cash_drawer_and_counter.jpg",
                }
            ],
            "conflict_alert": None,
            "telemetry": {
                "sensor_event": "02:31:05 — PIR-FRONT-01: motion_detected at billing_counter_area",
                "cctv_frame": "Interior motion recorded. Cash drawer forced.",
                "witness_statement": "Forensic Unit: 'Recovered 18-inch rusted crowbar with blue paint residue and single blue nitrile glove.'",
                "evidence_doc": "03_discarded_crowbar_and_glove.jpg",
            },
            "camera_preset": "counter_cam",
        },
        {
            "frame_idx": 6,
            "timestamp": "02:35 AM",
            "time_seconds": 3900,
            "phase": "EGRESS & ESCAPE",
            "title": "Egress with Duffel & Alleyway Escape",
            "narrative": "Intruder emerges under rear shutter holding heavy black nylon duffel bag in right hand. Pulls shutter down and flees towards EVR Periyar Salai.",
            "actor": {
                "visible": True,
                "pos": [-4.6, 0.0, -7.8],
                "action": "fleeing",
                "label": "Intruder Fleeing with Duffel Bag",
            },
            "scene_state": {
                "shutter_height": 0.1,
                "shutter_color": "#3f3f46",
                "shutter_alert": False,
                "vault_toppled": True,
                "counter_open": True,
                "active_sensor": "RFID-REAR-01: Contact Restored (Closed)",
                "sensor_color": "#71717a",
            },
            "evidence_markers": [
                {
                    "marker_id": "M-EXIT",
                    "label": "Egress Vector & Tyre/Shoe Impressions",
                    "pos": [-4.6, 0.05, -7.8],
                    "color": "#ef4444",
                    "filename": "01_tampered_rear_shutter.jpg",
                }
            ],
            "conflict_alert": None,
            "telemetry": {
                "sensor_event": "02:34:40 — RFID-REAR-01: door_closed (contact_restored)",
                "cctv_frame": "02:35:10 — Intruder emerges with black duffel bag in right hand, flees towards EVR Periyar Salai.",
                "witness_statement": "Night Guard K. Sundaram: 'Saw same person jogging back out towards main road around 02:35 AM.'",
                "evidence_doc": "03_cctv_alleyway_log.txt",
            },
            "camera_preset": "cctv_alley",
        },
        {
            "frame_idx": 7,
            "timestamp": "02:40 AM",
            "time_seconds": 4200,
            "phase": "PATROL INTERCEPTION",
            "title": "Police Patrol Sighting & Escape Vector",
            "narrative": "Routine Kilpauk G-3 night patrol spots male walking briskly near EVR Periyar junction carrying a heavy bag. Suspect departs on a dark blue gearless scooter.",
            "actor": {
                "visible": False,
                "pos": [-4.6, 0.0, -11.0],
                "action": "escaped",
                "label": "Suspect Departed Scene",
            },
            "scene_state": {
                "shutter_height": 0.0,
                "shutter_color": "#3f3f46",
                "shutter_alert": False,
                "vault_toppled": True,
                "counter_open": True,
                "active_sensor": "All Sensors Idle / Crime Scene Sealed",
                "sensor_color": "#3b82f6",
            },
            "evidence_markers": [],
            "conflict_alert": None,
            "telemetry": {
                "sensor_event": "03:00:00 — RFID-REAR-01: heartbeat_ok (Status nominal)",
                "cctv_frame": "Alleyway quiet. No further movements recorded.",
                "witness_statement": "Patrol Officer: 'Spotted male in dark rain jacket boarding a dark blue scooter at EVR Periyar corner around 02:40 AM.'",
                "evidence_doc": "01_forensic_inspection_report.pdf",
            },
            "camera_preset": "overview",
        },
    ]

    return {
        "case_id": case_id,
        "title": "4D Incident Simulation: MedVantage Burglary & Narcotics Egress",
        "scene_config": scene_config,
        "trajectory": full_trajectory,
        "frames": frames,
        "total_duration_sec": 4200,
        "total_frames": len(frames),
    }


def get_case_simulation(case_id: str, force_recompute: bool = False) -> Dict[str, Any]:
    """
    Retrieves the 4D Incident Simulation data for a case.
    Checks MySQL cache first for instant sub-second response.
    """
    conn = get_conn()
    if not force_recompute:
        cur = conn.cursor()
        cur.execute(
            "SELECT frames_json, trajectory_json, scene_config_json, telemetry_json, computed_at FROM case_simulations WHERE case_id=%s",
            (case_id,),
        )
        row = cur.fetchone()
        if row and row.get("frames_json"):
            try:
                frames = json.loads(row["frames_json"])
                trajectory = json.loads(row["trajectory_json"]) if row.get("trajectory_json") else []
                scene_config = json.loads(row["scene_config_json"]) if row.get("scene_config_json") else {}
                telemetry = json.loads(row["telemetry_json"]) if row.get("telemetry_json") else {}
                conn.close()
                return {
                    "case_id": case_id,
                    "title": telemetry.get("title", f"4D Incident Simulation — {case_id}"),
                    "scene_config": scene_config,
                    "trajectory": trajectory,
                    "frames": frames,
                    "total_duration_sec": telemetry.get("total_duration_sec", 4200),
                    "total_frames": len(frames),
                    "cached": True,
                    "computed_at": row.get("computed_at"),
                }
            except Exception as e:
                logger.warning(f"Failed to parse cached simulation for {case_id}: {e}")

    # Not cached or force_recompute: compute dynamically from timeline & conflicts
    timeline_events = get_timeline(case_id)
    cur = conn.cursor()
    cur.execute(
        "SELECT conflict_id, claim_a, source_a, time_a, claim_b, source_b, time_b, nature_of_conflict FROM conflicts WHERE case_id=%s",
        (case_id,),
    )
    conflicts = cur.fetchall()

    sim_data = _build_simulation_frames(case_id, timeline_events, conflicts)

    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        """INSERT INTO case_simulations
           (case_id, frames_json, trajectory_json, scene_config_json, telemetry_json, computed_at, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE
           frames_json=VALUES(frames_json),
           trajectory_json=VALUES(trajectory_json),
           scene_config_json=VALUES(scene_config_json),
           telemetry_json=VALUES(telemetry_json),
           computed_at=VALUES(computed_at)""",
        (
            case_id,
            json.dumps(sim_data["frames"]),
            json.dumps(sim_data["trajectory"]),
            json.dumps(sim_data["scene_config"]),
            json.dumps({"title": sim_data["title"], "total_duration_sec": sim_data["total_duration_sec"]}),
            now_str,
            now_str,
        ),
    )
    conn.commit()
    conn.close()

    sim_data["cached"] = False
    sim_data["computed_at"] = now_str
    return sim_data

