"""
Deterministic scene geometry for the sandbox (schema 3).

Handles any number of rectangular rooms (shared walls, several floors joined by
stairs), the outdoor area round the building, furniture, outdoor objects,
cameras/witnesses (line of sight) and any number of people.

Pure functions: no database, no model, no randomness. The model proposes room
sizes and how rooms attach, door/furniture positions as fractions, and step
sequences that reference places by id. It never writes a coordinate. Everything
here turns that into real geometry, routes each person around walls and
furniture, gives walking time from distance, and an independent validator
(`validate_plan`) re-checks every leg without using the router.

World axes: x runs east-west, z north-south, y is up. A room's `rect` is
(x0, x1, z0, z1) along its wall centre-lines; walls are WALL_THICKNESS_M thick.
"""
from __future__ import annotations

import heapq
import json
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

ENGINE_VERSION = "3.0"
SCHEMA_VERSION = 3


def _cfg(name: str, default: float) -> float:
    raw = os.environ.get("SANDBOX_" + name.upper())
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# Every tunable lives here, so a run can record exactly which values produced it.
CONFIG: Dict[str, float] = {
    "wall_thickness_m": _cfg("wall_thickness_m", 0.30),
    "actor_radius_m": _cfg("actor_radius_m", 0.30),
    "door_inside_offset_m": _cfg("door_inside_offset_m", 0.60),
    "outside_offset_m": _cfg("outside_offset_m", 2.50),
    "min_passable_door_m": _cfg("min_passable_door_m", 0.70),
    "door_clear_depth_m": _cfg("door_clear_depth_m", 1.40),
    "jamb_solid_m": _cfg("jamb_solid_m", 0.50),
    "min_room_m": _cfg("min_room_m", 1.5),
    "max_room_m": _cfg("max_room_m", 60.0),
    "min_height_m": _cfg("min_height_m", 2.2),
    "max_height_m": _cfg("max_height_m", 6.0),
    "fixture_gap_m": _cfg("fixture_gap_m", 0.05),
    "stand_margin_m": _cfg("stand_margin_m", 0.005),
    "walk_speed_mps": _cfg("walk_speed_mps", 1.4),
    "run_speed_mps": _cfg("run_speed_mps", 3.5),
    "carry_speed_factor": _cfg("carry_speed_factor", 0.9),
    "accel_mps2": _cfg("accel_mps2", 1.2),
    "stairs_speed_factor": _cfg("stairs_speed_factor", 0.6),
    "stairs_slope_deg": _cfg("stairs_slope_deg", 35.0),
    "max_human_speed_mps": _cfg("max_human_speed_mps", 7.5),
    "slab_m": _cfg("slab_m", 0.30),
    "door_height_m": _cfg("door_height_m", 2.10),
    "camera_eye_m": _cfg("camera_eye_m", 2.60),
    "witness_eye_m": _cfg("witness_eye_m", 1.60),
    "los_target_height_m": _cfg("los_target_height_m", 1.20),
    "people_overlap_m": _cfg("people_overlap_m", 0.45),
}
WALL_THICKNESS_M = CONFIG["wall_thickness_m"]
ACTOR_RADIUS_M = CONFIG["actor_radius_m"]
DOOR_INSIDE_OFFSET_M = CONFIG["door_inside_offset_m"]
OUTSIDE_OFFSET_M = CONFIG["outside_offset_m"]
MIN_PASSABLE_DOOR_M = CONFIG["min_passable_door_m"]
DOOR_CLEAR_DEPTH_M = CONFIG["door_clear_depth_m"]
JAMB_SOLID_M = CONFIG["jamb_solid_m"]
FIXTURE_GAP_M = CONFIG["fixture_gap_m"]
STAND_MARGIN_M = CONFIG["stand_margin_m"]
MAX_HUMAN_SPEED_MPS = CONFIG["max_human_speed_mps"]
DOOR_HEIGHT_M = CONFIG["door_height_m"]
MAX_STEPS = 60
MAX_ACTORS = 8
MAX_ROOMS = 24
MAX_FIXTURES_PER_ROOM = 30
MAX_OPENINGS = 60
MAX_OBSERVERS = 12
MAX_OUTDOOR = 20
MAX_LEVELS = (-1, 5)
BOX_TOLERANCE_M = 0.02  # the planner snaps to a grid; a path within 2 cm of the edge of an obstacle's clearance zone is not a collision
RESERVED_IDS = {"exterior", "outside", "none", "all"}

SIDES = ("north", "south", "east", "west")
OPENING_STATES = ("forced", "intact", "locked", "open", "unknown")
EFFECT_STATES = ("forced", "opened", "closed", "locked", "unlocked", "disturbed", "moved", "damaged")
ACTOR_COLORS = ["#ef4444", "#3b82f6", "#22c55e", "#f59e0b", "#a855f7", "#14b8a6", "#ec4899", "#eab308"]

ACTIONS = (
    "approach", "enter", "move", "search", "take_item", "struggle", "damage", "flee", "other",
    "wait", "hide", "look", "open", "close", "drop_item", "unlock", "lie_down", "sit", "stand",
    "shout", "call", "hand_over", "receive", "restrain",
)
DWELL_MIN_S = {
    "approach": 0.0, "enter": 0.0, "move": 0.0, "flee": 0.0, "search": 6.0, "take_item": 4.0, "struggle": 6.0,
    "damage": 5.0, "other": 2.0, "wait": 3.0, "hide": 3.0, "look": 3.0, "open": 3.0, "close": 3.0,
    "drop_item": 3.0, "unlock": 4.0, "lie_down": 3.0, "sit": 3.0, "stand": 1.0, "shout": 2.0, "call": 5.0,
    "hand_over": 3.0, "receive": 3.0, "restrain": 6.0,
}
UNLOCKING_ACTIONS = ("damage", "open", "unlock")

CHECKS_RUN = [
    "nobody passes through a wall except through a door opening wide enough for a person",
    "nobody passes through furniture or other objects (body radius included)",
    "every stop is on walkable floor, and every walk is continuous from step to step",
    "every place the scenario uses can be reached from outside the building",
    "doors recorded as locked are not passed before someone forces or opens them",
    "movement between steps that evidence puts on the clock is long enough to walk the distance",
    "where a camera or witness is claimed to have seen a step, walls and furniture do not block the view",
]
CHECKS_NOT_RUN = [
    "windows and glass (only doors, stairs and open boundaries are modelled)",
    "vehicles moving, or any terrain other than flat ground and stairs",
    "object physics (falling, breaking, moving furniture)",
    "people blocking each other, or physical contact between people",
    "whether a person's injuries, load or intent changed their speed",
    "sound, lighting and weather",
]

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
Rect = Tuple[float, float, float, float]  # x0, x1, z0, z1


def config_snapshot() -> Dict[str, Any]:
    return {"engine_version": ENGINE_VERSION, "schema_version": SCHEMA_VERSION, **CONFIG}


# --------------------------------------------------------------------------
# Safe coercion: model output is untrusted text, never assumed numeric
# --------------------------------------------------------------------------

def to_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        x = float(v)
    elif isinstance(v, str):
        m = _NUM_RE.search(v.replace(",", ""))
        x = float(m.group()) if m else None
    else:
        x = None
    if x is None or math.isnan(x) or math.isinf(x):
        return default
    return x


def to_seconds(v: Any, default: float) -> float:
    x = to_float(v, None)
    if x is None:
        return default
    if isinstance(v, str):
        low = v.lower()
        if "hour" in low or re.search(r"\bhrs?\b", low):
            x *= 3600
        elif "min" in low:
            x *= 60
    return x


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def normalize_id(v: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(v or "").strip().lower()).strip("_")[:40]


def clean_text(v: Any, limit: int) -> str:
    if v is None or isinstance(v, (dict, list)):
        return ""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(v)).strip()[:limit]


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _frac2(v: Any) -> Tuple[float, float]:
    lst = _as_list(v)
    return (clamp(to_float(lst[0] if len(lst) > 0 else None, 0.5) or 0.0, 0.0, 1.0),
            clamp(to_float(lst[1] if len(lst) > 1 else None, 0.5) or 0.0, 0.0, 1.0))


def _dist(a, b) -> float:
    return math.hypot(b[0] - a[0], b[2] - a[2])


def _polyline_len(pts) -> float:
    return sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


# --------------------------------------------------------------------------
# Rectangle maths
# --------------------------------------------------------------------------

def _in_rect(p, r: Rect, eps: float = 1e-9) -> bool:
    return r[0] - eps <= p[0] <= r[1] + eps and r[2] - eps <= p[2] <= r[3] + eps


def _strictly_in_rect(p, r: Rect, eps: float = 1e-7) -> bool:
    return r[0] + eps < p[0] < r[1] - eps and r[2] + eps < p[2] < r[3] - eps


def _seg_hits_rect(a, b, r: Rect, eps: float = 1e-7) -> bool:
    x0, x1, z0, z1 = r[0] + eps, r[1] - eps, r[2] + eps, r[3] - eps
    if x0 >= x1 or z0 >= z1:
        return False
    dx, dz = b[0] - a[0], b[2] - a[2]
    t0, t1 = 0.0, 1.0
    for p, q, lo, hi in ((dx, a[0], x0, x1), (dz, a[2], z0, z1)):
        if abs(p) < 1e-12:
            if q <= lo or q >= hi:
                return False
        else:
            ta, tb = (lo - q) / p, (hi - q) / p
            if ta > tb:
                ta, tb = tb, ta
            t0, t1 = max(t0, ta), min(t1, tb)
            if t0 >= t1:
                return False
    return t1 - t0 > 1e-9


def _overlap_area(a: Rect, b: Rect) -> float:
    ox = min(a[1], b[1]) - max(a[0], b[0])
    oz = min(a[3], b[3]) - max(a[2], b[2])
    return ox * oz if ox > 1e-6 and oz > 1e-6 else 0.0


def _overlap_push(a: Rect, b: Rect) -> Optional[Tuple[float, float]]:
    ox = min(a[1], b[1]) - max(a[0], b[0])
    oz = min(a[3], b[3]) - max(a[2], b[2])
    if ox <= 1e-9 or oz <= 1e-9:
        return None
    acx, acz = (a[0] + a[1]) / 2, (a[2] + a[3]) / 2
    bcx, bcz = (b[0] + b[1]) / 2, (b[2] + b[3]) / 2
    if ox < oz:
        return ((ox + FIXTURE_GAP_M) * (1 if acx >= bcx else -1), 0.0)
    return (0.0, (oz + FIXTURE_GAP_M) * (1 if acz >= bcz else -1))


def _shrink(r: Rect, d: float) -> Rect:
    return (r[0] + d, r[1] - d, r[2] + d, r[3] - d)


def _expand(r: Rect, d: float) -> Rect:
    return (r[0] - d, r[1] + d, r[2] - d, r[3] + d)


def _fixture_rect(fx: dict) -> Rect:
    return (fx["pos"][0] - fx["footprint_m"][0] / 2, fx["pos"][0] + fx["footprint_m"][0] / 2,
            fx["pos"][2] - fx["footprint_m"][1] / 2, fx["pos"][2] + fx["footprint_m"][1] / 2)


def _room_rect(room: dict) -> Rect:
    r = room["rect"]
    return (r[0], r[1], r[2], r[3])


# --------------------------------------------------------------------------
# Layout construction
# --------------------------------------------------------------------------

def _basis(raw_basis: Any, refs: List[str]) -> str:
    b = str(raw_basis or "").lower()
    if b in ("officer", "measured"):
        return "officer"  # supplied or measured by an investigator through the editor
    if not refs:
        return "assumed"
    return "stated" if b == "stated" else "inferred"


def _attach_rect(parent: Rect, w: float, l: float, side: str, a: float) -> Rect:
    px0, px1, pz0, pz1 = parent
    pw, pl = px1 - px0, pz1 - pz0
    if side == "east":
        z0 = pz0 + a * (pl - l)
        return (px1, px1 + w, z0, z0 + l)
    if side == "west":
        z0 = pz0 + a * (pl - l)
        return (px0 - w, px0, z0, z0 + l)
    x0 = px0 + a * (pw - w)
    if side == "north":
        return (x0, x0 + w, pz1, pz1 + l)
    return (x0, x0 + w, pz0 - l, pz0)


def _place_rooms(specs: List[dict], warnings: List[str]) -> List[dict]:
    """Lays rooms out from attachment hints (never from model coordinates).
    Rooms that cannot be placed without overlapping are moved to another side
    (and flagged) or dropped (and reported)."""
    placed: Dict[str, dict] = {}

    def overlaps(rect: Rect, level: int, ignore: str = "") -> bool:
        return any(r["level"] == level and r["id"] != ignore and _overlap_area(rect, _room_rect(r)) > 0.04 for r in placed.values())

    def bbox() -> Rect:
        rs = [_room_rect(r) for r in placed.values()]
        return (min(r[0] for r in rs), max(r[1] for r in rs), min(r[2] for r in rs), max(r[3] for r in rs))

    pending = list(specs)
    first = pending.pop(0)
    w, l = first["width_m"], first["length_m"]
    placed[first["id"]] = {**first, "rect": (-w / 2, w / 2, -l / 2, l / 2), "placement_note": ""}
    progress = True
    while pending and progress:
        progress = False
        for sp in list(pending):
            att = sp.get("attach")
            if att is None:
                bb = bbox()
                x0 = bb[1] + 8.0
                placed[sp["id"]] = {**sp, "rect": (x0, x0 + sp["width_m"], bb[2], bb[2] + sp["length_m"]),
                                    "placement_note": "separate structure placed beside the others"}
                pending.remove(sp)
                progress = True
                continue
            parent = placed.get(att["to"])
            if parent is None:
                continue
            note = ""
            options: List[Tuple[Rect, int, str]] = []
            aligns = []
            for a in (att["align"], 0.5, 0.0, 1.0):
                if a not in aligns:
                    aligns.append(a)
            if att["wall"] in ("above", "below"):
                lvl = parent["level"] + (1 if att["wall"] == "above" else -1)
                px0, px1, pz0, pz1 = _room_rect(parent)
                for a in aligns:
                    options.append(((px0 + a * ((px1 - px0) - sp["width_m"]), px0 + a * ((px1 - px0) - sp["width_m"]) + sp["width_m"],
                                    pz0 + a * ((pz1 - pz0) - sp["length_m"]), pz0 + a * ((pz1 - pz0) - sp["length_m"]) + sp["length_m"]), lvl, ""))
            else:
                order = [att["wall"]] + [s for s in SIDES if s != att["wall"]]
                for i, side in enumerate(order):
                    for a in aligns:
                        options.append((_attach_rect(_room_rect(parent), sp["width_m"], sp["length_m"], side, a), parent["level"],
                                        "" if i == 0 else f"placed on the {side} side of '{parent['id']}' because the stated side overlapped another room"))
            chosen = None
            for rect, lvl, why in options:
                if not overlaps(rect, lvl):
                    chosen = (rect, lvl, why)
                    break
            if chosen is None:
                warnings.append(f"room '{sp['id']}' could not be placed next to '{att['to']}' without overlapping another room and was dropped")
                pending.remove(sp)
                continue
            rect, lvl, why = chosen
            if why:
                warnings.append(f"room '{sp['id']}' {why}")
            placed[sp["id"]] = {**sp, "rect": rect, "level": lvl, "placement_note": why}
            pending.remove(sp)
            progress = True
    for sp in pending:
        warnings.append(f"room '{sp['id']}' refers to '{(sp.get('attach') or {}).get('to')}', which is not a room that could be placed; it was dropped")
    return list(placed.values())


def _level_floors(rooms: List[dict]) -> List[dict]:
    by_level: Dict[int, float] = {}
    for r in rooms:
        by_level[r["level"]] = max(by_level.get(r["level"], 0.0), r["height_m"])
    floors: Dict[int, float] = {0: 0.0}
    for lv in sorted(l for l in by_level if l > 0):
        floors[lv] = floors.get(lv - 1, 0.0) + by_level.get(lv - 1, 2.6) + CONFIG["slab_m"]
    for lv in sorted((l for l in by_level if l < 0), reverse=True):
        floors[lv] = floors.get(lv + 1, 0.0) - by_level.get(lv, 2.6) - CONFIG["slab_m"]
    return [{"level": lv, "floor_y": round(floors[lv], 3), "height_m": by_level.get(lv, 2.6)} for lv in sorted(floors)]


def _shared_edge(a: dict, b: dict) -> Optional[dict]:
    if a["level"] != b["level"]:
        return None
    ra, rb = _room_rect(a), _room_rect(b)
    tol = 1e-3
    best: Optional[dict] = None

    def consider(wall: str, lo: float, hi: float, line: float, orient: str):
        nonlocal best
        if hi - lo > 0.2 and (best is None or hi - lo > best["hi"] - best["lo"]):
            best = {"wall": wall, "lo": lo, "hi": hi, "line": line, "orient": orient}

    if abs(ra[1] - rb[0]) < tol:
        consider("east", max(ra[2], rb[2]), min(ra[3], rb[3]), ra[1], "z")
    if abs(ra[0] - rb[1]) < tol:
        consider("west", max(ra[2], rb[2]), min(ra[3], rb[3]), ra[0], "z")
    if abs(ra[3] - rb[2]) < tol:
        consider("north", max(ra[0], rb[0]), min(ra[1], rb[1]), ra[3], "x")
    if abs(ra[2] - rb[3]) < tol:
        consider("south", max(ra[0], rb[0]), min(ra[1], rb[1]), ra[2], "x")
    return best


def _edge_of(room: dict, wall: str) -> Tuple[str, float, float, float]:
    x0, x1, z0, z1 = _room_rect(room)
    if wall == "east":
        return "z", x1, z0, z1
    if wall == "west":
        return "z", x0, z0, z1
    if wall == "north":
        return "x", z1, x0, x1
    return "x", z0, x0, x1


def _exterior_intervals(room: dict, wall: str, rooms: List[dict]) -> List[Tuple[float, float]]:
    orient, line, e0, e1 = _edge_of(room, wall)
    covered: List[Tuple[float, float]] = []
    for other in rooms:
        if other["id"] == room["id"] or other["level"] != room["level"]:
            continue
        for ow in SIDES:
            o_orient, o_line, o0, o1 = _edge_of(other, ow)
            if o_orient == orient and abs(o_line - line) < 1e-3:
                lo, hi = max(e0, o0), min(e1, o1)
                if hi - lo > 1e-6:
                    covered.append((lo, hi))
    covered.sort()
    out, cur = [], e0
    for lo, hi in covered:
        if lo > cur + 1e-6:
            out.append((cur, lo))
        cur = max(cur, hi)
    if cur < e1 - 1e-6:
        out.append((cur, e1))
    return out


def _gap_points(orient: str, wall: str, line: float, c: float) -> Dict[str, List[float]]:
    inner, out = DOOR_INSIDE_OFFSET_M, OUTSIDE_OFFSET_M
    if orient == "z":  # wall at x = line, door centred at z = c
        s = -1 if wall == "east" else 1  # direction into room A
        return {"gap_pos": [line, 0.0, c], "pos_a": [line + s * inner, 0.0, c], "pos_b": [line - s * inner, 0.0, c],
                "outside_pos": [line - s * out, 0.0, c]}
    s = -1 if wall == "north" else 1
    return {"gap_pos": [c, 0.0, line], "pos_a": [c, 0.0, line + s * inner], "pos_b": [c, 0.0, line - s * inner],
            "outside_pos": [c, 0.0, line - s * out]}


def _zone_in_room(op: dict, room_id: str) -> Rect:
    """Rectangle in front of an opening, on the given room's side, that furniture may not occupy."""
    t2 = CONFIG["wall_thickness_m"] / 2
    half = op["width_m"] / 2 + 0.4
    c, d, line = op["gap_center_m"], DOOR_CLEAR_DEPTH_M, op["line"]
    is_a = room_id == op["room_a"]
    wall = op["wall"]
    into = (-1 if wall in ("east", "north") else 1) * (1 if is_a else -1)
    lo, hi = (line + t2, line + t2 + d) if into > 0 else (line - t2 - d, line - t2)
    return (lo, hi, c - half, c + half) if op["orient"] == "z" else (c - half, c + half, lo, hi)


def _place_fixture_group(room_rect: Rect, items: List[dict], zones: List[Rect], warnings: List[str], label: str) -> None:
    """Places furniture inside one room: inside the walls, apart from each other and from door zones."""
    t2 = CONFIG["wall_thickness_m"] / 2
    inner = _shrink(room_rect, t2)
    for fx in items:
        fw, fd = fx["footprint_m"]
        fw_max, fd_max = (inner[1] - inner[0]) - 0.2, (inner[3] - inner[2]) - 0.2
        shrunk = fw > fw_max or fd > fd_max
        fw, fd = max(0.1, min(fw, fw_max)), max(0.1, min(fd, fd_max))
        fx["footprint_m"] = [round(fw, 3), round(fd, 3)]
        lo_x, hi_x = inner[0] + fw / 2, inner[1] - fw / 2
        lo_z, hi_z = inner[2] + fd / 2, inner[3] - fd / 2
        fx["_bounds"] = (lo_x, hi_x, lo_z, hi_z)
        px, pz = fx["position_frac"]
        fx["pos"] = [round(lo_x + px * (hi_x - lo_x), 3), 0.0, round(lo_z + pz * (hi_z - lo_z), 3)]
        fx["adjusted"] = False
        fx["adjust_notes"] = ["footprint reduced to fit the room"] if shrunk else []
        if shrunk:
            warnings.append(f"{label} '{fx['id']}' was larger than its room and was reduced to fit")
    originals = {fx["id"]: list(fx["pos"]) for fx in items}
    for _ in range(80):
        moved = False
        for i, fx in enumerate(items):
            lo_x, hi_x, lo_z, hi_z = fx["_bounds"]
            for zone in zones:
                push = _overlap_push(_fixture_rect(fx), zone)
                if push:
                    fx["pos"][0] = clamp(fx["pos"][0] + push[0], lo_x, hi_x)
                    fx["pos"][2] = clamp(fx["pos"][2] + push[1], lo_z, hi_z)
                    moved = True
            for j in range(i):
                push = _overlap_push(_fixture_rect(fx), _fixture_rect(items[j]))
                if push:
                    fx["pos"][0] = clamp(fx["pos"][0] + push[0], lo_x, hi_x)
                    fx["pos"][2] = clamp(fx["pos"][2] + push[1], lo_z, hi_z)
                    moved = True
        if not moved:
            break
    # A piece that still covers a doorway after being pushed around is cut back instead of left
    # blocking the only way in: the model's size for it was an estimate, a shelf cannot run across a door.
    for fx in items:
        for zone in zones:
            if not _overlap_push(_fixture_rect(fx), zone):
                continue
            x0, x1, z0, z1 = _fixture_rect(fx)
            parts = [(x0, min(x1, zone[0]), z0, z1), (max(x0, zone[1]), x1, z0, z1), (x0, x1, z0, min(z1, zone[2])), (x0, x1, max(z0, zone[3]), z1)]
            parts = [p for p in parts if p[1] - p[0] >= 0.25 and p[3] - p[2] >= 0.25]
            if not parts:
                continue
            best = max(parts, key=lambda p: (p[1] - p[0]) * (p[3] - p[2]))
            before = list(fx["footprint_m"])
            fx["footprint_m"] = [round(best[1] - best[0], 3), round(best[3] - best[2], 3)]
            fx["pos"] = [round((best[0] + best[1]) / 2, 3), 0.0, round((best[2] + best[3]) / 2, 3)]
            fx["adjusted"] = True
            fx["adjust_notes"].append(f"cut back from {before[0]:.1f} x {before[1]:.1f} m to {fx['footprint_m'][0]:.1f} x {fx['footprint_m'][1]:.1f} m to leave the doorway clear")
            warnings.append(f"{label} '{fx['id']}' was cut back from {before[0]:.1f} x {before[1]:.1f} m to {fx['footprint_m'][0]:.1f} x {fx['footprint_m'][1]:.1f} m because it would have blocked a doorway")
    for fx in items:
        fx["pos"] = [round(fx["pos"][0], 3), 0.0, round(fx["pos"][2], 3)]
        o = originals[fx["id"]]
        moved_m = math.hypot(fx["pos"][0] - o[0], fx["pos"][2] - o[2])
        if moved_m > 0.01:
            fx["adjusted"] = True
            fx["adjust_notes"].append(f"moved {moved_m:.2f} m to avoid overlapping furniture or blocking a door")
            warnings.append(f"{label} '{fx['id']}' moved {moved_m:.2f} m to avoid overlap or a blocked door")
        fx["requested_pos"] = [round(o[0], 3), 0.0, round(o[2], 3)]
        del fx["_bounds"]
    for i, a in enumerate(items):
        for b in items[:i]:
            if _overlap_push(_fixture_rect(a), _fixture_rect(b)):
                warnings.append(f"{label}s '{a['id']}' and '{b['id']}' could not be separated (room too small) and overlap")
        for zone in zones:
            if _overlap_push(_fixture_rect(a), zone):
                warnings.append(f"{label} '{a['id']}' could not be moved clear of a doorway (room too small)")


def build_layout(raw: Any, known_refs: set) -> Dict[str, Any]:
    """Turns untrusted model layout JSON into a geometrically valid scene.

    Guarantees (property-tested): rooms never overlap on a floor; every door
    lies on a real shared or exterior wall and fits it; furniture lies fully
    inside its room and clear of doors; every element carries a basis
    (stated / inferred / assumed). Nothing is invented silently: defaults and
    adjustments are recorded in `warnings` / `defaults_used`.
    """
    if not isinstance(raw, dict):
        raw = {}
    warnings: List[str] = []
    defaults: List[str] = []
    limits: List[str] = []
    t2 = CONFIG["wall_thickness_m"] / 2

    def refs_of(v: Any) -> List[str]:
        out, seen = [], set()
        for r in _as_list(v):
            s = str(r).strip()
            if s in known_refs and s not in seen:
                seen.add(s)
                out.append(s)
        return out[:8]

    used: set = set(RESERVED_IDS)

    def take_id(v: Any) -> Optional[str]:
        i = normalize_id(v)
        if not i or i in used:
            return None
        used.add(i)
        return i

    # ---- rooms (supports the older single-room shape too) --------------------
    raw_rooms = [r for r in _as_list(raw.get("rooms")) if isinstance(r, dict)]
    if not raw_rooms:
        raw_rooms = [{"id": "main", "label": "Main room", "width_m": raw.get("width_m"), "length_m": raw.get("length_m"),
                      "height_m": raw.get("height_m"), "dimensions_basis": raw.get("dimensions_basis")}]
    if len(raw_rooms) > MAX_ROOMS:
        limits.append(f"only the first {MAX_ROOMS} rooms are modelled")
    specs: List[dict] = []
    for it in raw_rooms[:MAX_ROOMS]:
        rid = take_id(it.get("id")) or take_id(f"room_{len(specs) + 1}")
        w0, l0 = to_float(it.get("width_m")), to_float(it.get("length_m"))
        dim_basis = str(it.get("dimensions_basis") or "assumed").lower()
        if dim_basis not in ("stated", "inferred", "assumed", "measured"):
            dim_basis = "assumed"
        if w0 is None or l0 is None:
            dim_basis = "assumed"
            defaults.append(f"size of room '{rid}' not usable in the model output; defaulted to {6 if len(raw_rooms) > 1 else 10} m x {5 if len(raw_rooms) > 1 else 10} m")
        dw, dl = (6.0, 5.0) if len(raw_rooms) > 1 else (10.0, 10.0)
        w = clamp(w0 if w0 is not None else dw, CONFIG["min_room_m"], CONFIG["max_room_m"])
        l = clamp(l0 if l0 is not None else dl, CONFIG["min_room_m"], CONFIG["max_room_m"])
        if (w0 is not None and abs(w - w0) > 1e-6) or (l0 is not None and abs(l - l0) > 1e-6):
            limits.append(f"room '{rid}' size {w0}x{l0} m was limited to {w:.1f}x{l:.1f} m")
        if dim_basis == "assumed":
            defaults.append(f"size of room '{rid}' ({w:.1f} m x {l:.1f} m) is an assumption, not measured or stated in evidence")
        h0 = to_float(it.get("height_m"))
        h = clamp(h0 if h0 is not None else 3.0, CONFIG["min_height_m"], CONFIG["max_height_m"])
        att = it.get("attach") if isinstance(it.get("attach"), dict) else None
        attach = None
        if att:
            wall = str(att.get("wall") or "").lower()
            a = to_float(att.get("align_frac"), 0.5)
            attach = {"to": normalize_id(att.get("to")), "wall": wall if wall in SIDES + ("above", "below") else "east",
                      "align": clamp(a if a is not None else 0.5, 0.0, 1.0)}
        refs = refs_of(it.get("evidence_refs"))
        lv = to_float(it.get("level"), 0.0)
        specs.append({
            "id": rid, "label": clean_text(it.get("label"), 80) or rid, "width_m": round(w, 3), "length_m": round(l, 3),
            "height_m": round(h, 3), "level": int(clamp(round(lv or 0), MAX_LEVELS[0], MAX_LEVELS[1])), "attach": attach,
            "dimensions_basis": dim_basis, "observed": it.get("observed") is not False,
            "evidence_refs": refs, "basis": _basis(it.get("basis"), refs),
        })
    rooms = _place_rooms(specs, warnings)
    room_by_id = {r["id"]: r for r in rooms}
    first_room = rooms[0]["id"]
    floors = _level_floors(rooms)
    floor_y = {f["level"]: f["floor_y"] for f in floors}
    for r in rooms:
        r["rect"] = [round(v, 3) for v in r["rect"]]
        r["floor_y"] = floor_y[r["level"]]
        r["width_m"] = round(r["rect"][1] - r["rect"][0], 3)
        r["length_m"] = round(r["rect"][3] - r["rect"][2], 3)
    if any(r["dimensions_basis"] == "assumed" for r in rooms) and all(r["dimensions_basis"] == "assumed" for r in rooms):
        dim_basis_overall = "assumed"
    else:
        dim_basis_overall = "stated" if all(r["dimensions_basis"] in ("stated", "measured") for r in rooms) else "inferred"

    def room_of(v: Any, kind: str, ident: str) -> str:
        rid = normalize_id(v)
        if rid in room_by_id:
            return rid
        if v:
            warnings.append(f"{kind} '{ident}' named an unknown room; it was placed in '{first_room}'")
        return first_room

    # ---- openings -------------------------------------------------------------
    openings: List[dict] = []
    wall_lines: Dict[Tuple[str, float, int], List[dict]] = {}

    def register(op: dict, orient: str, line: float, level: int) -> None:
        wall_lines.setdefault((orient, round(line, 3), level), []).append(op)

    def state_of(it: dict) -> str:
        s = str(it.get("state") or "unknown").lower()
        return s if s in OPENING_STATES else "unknown"

    for it in [c for c in _as_list(raw.get("connections")) if isinstance(c, dict)][:MAX_OPENINGS]:
        oid = take_id(it.get("id"))
        if not oid:
            continue
        ra, rb = room_by_id.get(normalize_id(it.get("room_a"))), room_by_id.get(normalize_id(it.get("room_b")))
        refs = refs_of(it.get("evidence_refs"))
        if ra is None or rb is None or ra is rb:
            warnings.append(f"connection '{oid}' does not link two known rooms and was dropped")
            continue
        kind = "stairs" if str(it.get("kind") or "").lower() == "stairs" or ra["level"] != rb["level"] else "door"
        width = clamp(to_float(it.get("width_m"), 1.0) or 1.0, 0.5, 6.0)
        frac = clamp(to_float(it.get("position_frac") if not isinstance(it.get("position_frac"), list) else None, 0.5) or 0.0, 0.0, 1.0)
        base = {"id": oid, "label": clean_text(it.get("label"), 80) or oid, "state": state_of(it), "state_note": clean_text(it.get("state_note"), 160),
                "evidence_refs": refs, "basis": _basis(it.get("basis"), refs), "room_a": ra["id"], "room_b": rb["id"]}
        if kind == "stairs":
            if abs(ra["level"] - rb["level"]) != 1:
                warnings.append(f"stairs '{oid}' must join rooms on neighbouring floors and was dropped")
                continue
            fx_, fz_ = _frac2(it.get("position_frac") if isinstance(it.get("position_frac"), list) else [0.5, 0.5])
            ia, ib = _shrink(_room_rect(ra), t2 + ACTOR_RADIUS_M + 0.1), _shrink(_room_rect(rb), t2 + ACTOR_RADIUS_M + 0.1)
            ov = (max(ia[0], ib[0]), min(ia[1], ib[1]), max(ia[2], ib[2]), min(ia[3], ib[3]))
            if ov[0] >= ov[1] or ov[2] >= ov[3]:
                warnings.append(f"stairs '{oid}': the two floors do not overlap in plan; stairs dropped")
                continue
            sx, sz = ov[0] + fx_ * (ov[1] - ov[0]), ov[2] + fz_ * (ov[3] - ov[2])
            vertical = abs(floor_y[ra["level"]] - floor_y[rb["level"]])
            op = {**base, "kind": "stairs", "wall": None, "orient": None, "line": 0.0, "level": ra["level"], "gap_center_m": 0.0,
                  "position_frac": [fx_, fz_], "width_m": round(width, 3), "passable": width >= MIN_PASSABLE_DOOR_M, "gap_pos": [round(sx, 3), 0.0, round(sz, 3)],
                  "pos_a": [round(sx, 3), 0.0, round(sz, 3)], "pos_b": [round(sx, 3), 0.0, round(sz, 3)], "outside_pos": None,
                  "vertical_m": round(vertical, 3)}
            openings.append(op)
            continue
        edge = _shared_edge(ra, rb)
        if edge is None:
            warnings.append(f"connection '{oid}': rooms '{ra['id']}' and '{rb['id']}' do not share a wall and the door was dropped")
            continue
        span = edge["hi"] - edge["lo"]
        half = min(width / 2, max(0.25, span / 2 - JAMB_SOLID_M))
        lo_c, hi_c = edge["lo"] + half + JAMB_SOLID_M, edge["hi"] - half - JAMB_SOLID_M
        if lo_c > hi_c:
            lo_c = hi_c = (edge["lo"] + edge["hi"]) / 2
        c = clamp(edge["lo"] + frac * span, lo_c, hi_c)
        op = {**base, "kind": "door", "wall": edge["wall"], "orient": edge["orient"], "line": edge["line"], "level": ra["level"],
              "position_frac": round(frac, 4), "gap_center_m": round(c, 3), "width_m": round(half * 2, 3), "passable": half * 2 >= MIN_PASSABLE_DOOR_M,
              "_span": (edge["lo"], edge["hi"])}
        register(op, edge["orient"], edge["line"], ra["level"])
        openings.append(op)

    n_external = 0
    for it in [e for e in _as_list(raw.get("entry_points")) if isinstance(e, dict)][:MAX_OPENINGS]:
        oid = take_id(it.get("id"))
        if not oid:
            continue
        room = room_by_id[room_of(it.get("room"), "entrance", oid)]
        wall = str(it.get("wall") or "").lower()
        if wall not in SIDES:
            wall = "south"
            warnings.append(f"entrance '{oid}' had no valid wall; the south wall was assumed")
        refs = refs_of(it.get("evidence_refs"))
        if room["level"] != 0:
            warnings.append(f"entrance '{oid}' is not on the ground floor; outside doors are only modelled at ground level, so it was dropped")
            continue
        width = clamp(to_float(it.get("width_m"), 1.0) or 1.0, 0.5, 6.0)
        frac = clamp(to_float(it.get("position_frac"), 0.5) or 0.0, 0.0, 1.0)
        orient, line, e0, e1 = _edge_of(room, wall)
        ivals = [iv for iv in _exterior_intervals(room, wall, rooms) if iv[1] - iv[0] >= 0.5 + 2 * JAMB_SOLID_M * 0.5]
        if not ivals:
            warnings.append(f"entrance '{oid}': the {wall} wall of '{room['id']}' has no outside-facing stretch and the door was dropped")
            continue
        c0 = e0 + frac * (e1 - e0)
        iv = min(ivals, key=lambda v: 0 if v[0] <= c0 <= v[1] else min(abs(c0 - v[0]), abs(c0 - v[1])))
        span = iv[1] - iv[0]
        half = min(width / 2, max(0.25, span / 2 - JAMB_SOLID_M * 0.5))
        lo_c, hi_c = iv[0] + half + JAMB_SOLID_M * 0.5, iv[1] - half - JAMB_SOLID_M * 0.5
        if lo_c > hi_c:
            lo_c = hi_c = (iv[0] + iv[1]) / 2
        c = clamp(c0, lo_c, hi_c)
        op = {"id": oid, "label": clean_text(it.get("label"), 80) or oid, "kind": "external", "room_a": room["id"], "room_b": None,
              "wall": wall, "orient": orient, "line": line, "level": 0, "position_frac": round(frac, 4), "gap_center_m": round(c, 3), "width_m": round(half * 2, 3),
              "state": state_of(it), "state_note": clean_text(it.get("state_note"), 160), "evidence_refs": refs,
              "basis": _basis(it.get("basis"), refs), "passable": half * 2 >= MIN_PASSABLE_DOOR_M, "_span": iv}
        register(op, orient, line, 0)
        openings.append(op)
        n_external += 1
    if n_external == 0:
        r0 = rooms[0] if rooms[0]["level"] == 0 else next((r for r in rooms if r["level"] == 0), rooms[0])
        placed_default = False
        for wall in ("south", "north", "east", "west"):
            ivals = _exterior_intervals(r0, wall, rooms)
            if ivals and r0["level"] == 0:
                iv = max(ivals, key=lambda v: v[1] - v[0])
                orient, line, _, _ = _edge_of(r0, wall)
                op = {"id": "main_entry", "label": "Main entrance (assumed)", "kind": "external", "room_a": r0["id"], "room_b": None,
                      "wall": wall, "orient": orient, "line": line, "level": 0, "gap_center_m": round((iv[0] + iv[1]) / 2, 3),
                      "width_m": 1.0, "state": "unknown", "state_note": "", "evidence_refs": [], "basis": "assumed", "passable": True, "_span": iv}
                used.add("main_entry")
                register(op, orient, line, 0)
                openings.append(op)
                defaults.append("no outside door was identified in evidence; one entrance is assumed")
                placed_default = True
                break
        if not placed_default:
            warnings.append("the building has no outside-facing wall at ground level, so nobody can enter")

    # resolve overlaps between openings sharing one wall line
    for key, ops in wall_lines.items():
        ops.sort(key=lambda o: o["gap_center_m"])
        prev_hi: Optional[float] = None
        for op in list(ops):
            half = op["width_m"] / 2
            lo_ok, hi_ok = op["_span"][0] + half + JAMB_SOLID_M * 0.5, op["_span"][1] - half - JAMB_SOLID_M * 0.5
            c = op["gap_center_m"]
            if prev_hi is not None:
                c = max(c, prev_hi + JAMB_SOLID_M + half)
            if c > hi_ok + 1e-6 or c < lo_ok - 1e-6 and lo_ok <= hi_ok:
                warnings.append(f"opening '{op['id']}' overlapped another opening on the same wall and was dropped")
                openings.remove(op)
                continue
            op["gap_center_m"] = round(c, 3)
            prev_hi = c + half
    for op in openings:
        if op["kind"] == "stairs":
            continue
        op.update({k: [round(x, 3) for x in v] for k, v in _gap_points(op["orient"], op["wall"], op["line"], op["gap_center_m"]).items()})
        if op["kind"] == "door":
            pass
        else:
            op["pos_b"] = None
        op.pop("_span", None)
        if not op["passable"]:
            warnings.append(f"opening '{op['id']}' is {op['width_m']:.2f} m wide, too narrow for a person to pass")

    # ---- furniture --------------------------------------------------------------
    fixtures: List[dict] = []
    for it in [f for f in _as_list(raw.get("fixtures")) if isinstance(f, dict)]:
        fid = take_id(it.get("id"))
        if not fid:
            continue
        room_id = room_of(it.get("room"), "furniture", fid)
        fp = _as_list(it.get("footprint_m"))
        refs = refs_of(it.get("evidence_refs"))
        color = it.get("color_hex")
        h = to_float(it.get("height_m"), 0.8)
        fixtures.append({
            "id": fid, "label": clean_text(it.get("label"), 80) or fid, "room": room_id, "position_frac": list(_frac2(it.get("position_frac"))),
            "footprint_m": [clamp(to_float(fp[0] if len(fp) > 0 else None, 0.6) or 0.6, 0.1, 6.0), clamp(to_float(fp[1] if len(fp) > 1 else None, 0.6) or 0.6, 0.1, 6.0)],
            "height_m": round(clamp(h if h is not None else 0.8, 0.1, min(2.5, room_by_id[room_id]["height_m"] - 0.1)), 3),
            "color_hex": color if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color) else "#8a7967",
            "category": clean_text(it.get("category"), 24).lower(),
            "evidence_refs": refs, "basis": _basis(it.get("basis"), refs),
        })
    stair_zones: Dict[str, List[Rect]] = {}
    for op in openings:
        if op["kind"] == "stairs":
            z = (op["gap_pos"][0] - 0.9, op["gap_pos"][0] + 0.9, op["gap_pos"][2] - 0.9, op["gap_pos"][2] + 0.9)
            stair_zones.setdefault(op["room_a"], []).append(z)
            stair_zones.setdefault(op["room_b"], []).append(z)
    for room in rooms:
        zones = [_zone_in_room(op, room["id"]) for op in openings if op["kind"] != "stairs" and room["id"] in (op["room_a"], op["room_b"])]
        zones += stair_zones.get(room["id"], [])
        group = [f for f in fixtures if f["room"] == room["id"]][:MAX_FIXTURES_PER_ROOM]
        _place_fixture_group(_room_rect(room), group, zones, warnings, "furniture")
    fixtures = [f for f in fixtures if "pos" in f]

    # ---- key locations ------------------------------------------------------------
    key_locations: List[dict] = []
    for it in [k for k in _as_list(raw.get("key_locations")) if isinstance(k, dict)][:40]:
        kid = take_id(it.get("id"))
        if not kid:
            continue
        refs = refs_of(it.get("evidence_refs"))
        base = {"id": kid, "label": clean_text(it.get("label"), 80) or kid, "significance": clean_text(it.get("significance"), 200),
                "evidence_refs": refs, "basis": _basis(it.get("basis"), refs)}
        if normalize_id(it.get("room")) == "outside":
            base["room"] = "outside"
            base["_near"] = {"near": normalize_id(it.get("near")), "distance_m": to_float(it.get("distance_m"), 3.0), "lateral_m": to_float(it.get("lateral_m"), 0.0)}
            base["pos"] = None
        else:
            room = room_by_id[room_of(it.get("room"), "place", kid)]
            walk = _shrink(_room_rect(room), t2 + ACTOR_RADIUS_M)
            fx_, fz_ = _frac2(it.get("position_frac"))
            base["room"] = room["id"]
            base["position_frac"] = [fx_, fz_]
            base["pos"] = [round(walk[0] + fx_ * (walk[1] - walk[0]), 3), 0.0, round(walk[2] + fz_ * (walk[3] - walk[2]), 3)]
        key_locations.append(base)

    # ---- things outside the building ------------------------------------------------
    externals = [op for op in openings if op["kind"] == "external"]

    def outside_point(near: str, distance: Optional[float], lateral: Optional[float]) -> Optional[List[float]]:
        op = next((o for o in externals if o["id"] == near), externals[0] if externals else None)
        if op is None:
            return None
        gx, _, gz = op["gap_pos"]
        ox, oz = op["outside_pos"][0] - gx, op["outside_pos"][2] - gz
        n = math.hypot(ox, oz) or 1.0
        ux, uz = ox / n, oz / n
        d = clamp(distance if distance is not None else 3.0, 0.6, 25.0) + OUTSIDE_OFFSET_M - 1.0
        lat = clamp(lateral if lateral is not None else 0.0, -15.0, 15.0)
        for _ in range(80):  # sideways offsets can land inside the building: walk outward until clear
            px, pz = gx + ux * d - uz * lat, gz + uz * d + ux * lat
            if not any(_strictly_in_rect([px, 0.0, pz], _expand(r, ACTOR_RADIUS_M + 0.2)) for r in outer_rects):
                return [round(px, 3), 0.0, round(pz, 3)]
            d += 0.5
        return None

    outer_rects = [_expand(_room_rect(r), t2) for r in rooms if r["level"] == 0]
    outdoor_objects: List[dict] = []
    for it in [o for o in _as_list(raw.get("outdoor_objects")) if isinstance(o, dict)][:MAX_OUTDOOR]:
        oid = take_id(it.get("id"))
        if not oid:
            continue
        pt = outside_point(normalize_id(it.get("near")), to_float(it.get("distance_m"), 3.0), to_float(it.get("lateral_m"), 0.0))
        fp = _as_list(it.get("footprint_m"))
        fw = clamp(to_float(fp[0] if len(fp) > 0 else None, 1.0) or 1.0, 0.2, 8.0)
        fd = clamp(to_float(fp[1] if len(fp) > 1 else None, 1.0) or 1.0, 0.2, 8.0)
        refs = refs_of(it.get("evidence_refs"))
        if pt is None:
            warnings.append(f"outdoor object '{oid}' has no outside door to be placed beside and was dropped")
            continue
        box = (pt[0] - fw / 2, pt[0] + fw / 2, pt[2] - fd / 2, pt[2] + fd / 2)
        asked_pt = list(pt)
        # an object must not sit on the way in: the strip from an outside door to where people arrive, and a little beyond
        for _ in range(60):
            hit = None
            for op in externals:
                g, o = op["gap_pos"], op["outside_pos"]
                nx, nz = o[0] - g[0], o[2] - g[2]
                ln = math.hypot(nx, nz) or 1.0
                nx, nz = nx / ln, nz / ln
                r = ACTOR_RADIUS_M + 0.35
                ex, ez = o[0] + nx * 0.8, o[2] + nz * 0.8
                strip = (min(g[0], ex) - r, max(g[0], ex) + r, min(g[2], ez) - r, max(g[2], ez) + r)
                if _overlap_area(box, strip) > 0:
                    hit = (op, nx, nz)
                    break
            if hit is None:
                break
            op, nx, nz = hit
            lx, lz = -nz, nx  # sideways, along the wall
            side = (pt[0] - op["outside_pos"][0]) * lx + (pt[2] - op["outside_pos"][2]) * lz
            sgn = 1.0 if side >= 0 else -1.0
            pt = [round(pt[0] + lx * sgn * 0.5, 3), 0.0, round(pt[2] + lz * sgn * 0.5, 3)]
            box = (pt[0] - fw / 2, pt[0] + fw / 2, pt[2] - fd / 2, pt[2] + fd / 2)
        if any(_overlap_area(box, r) > 0 for r in outer_rects):
            warnings.append(f"outdoor object '{oid}' would overlap the building and was dropped")
            continue
        h = to_float(it.get("height_m"), 1.2)
        kind = str(it.get("kind") or "object").lower()
        outdoor_objects.append({"id": oid, "label": clean_text(it.get("label"), 80) or oid, "kind": kind if kind in ("vehicle", "object", "fence", "tree") else "object",
                                "room": "outside", "pos": pt, "footprint_m": [round(fw, 3), round(fd, 3)],
                                "height_m": round(clamp(h if h is not None else 1.2, 0.1, 4.0), 3), "color_hex": "#64748b",
                                "evidence_refs": refs, "basis": _basis(it.get("basis"), refs), "adjusted": asked_pt != pt,
                                "adjust_notes": ["moved clear of the spot where people arrive at the door"] if asked_pt != pt else [], "requested_pos": asked_pt})
    for kl in key_locations:
        if kl.get("room") == "outside":
            n = kl.pop("_near")
            pt = outside_point(n["near"], n["distance_m"], n["lateral_m"])
            if pt is None:
                warnings.append(f"place '{kl['id']}' outside has no door to be placed beside and was dropped")
                kl["pos"] = None
                continue
            kl["pos"] = pt
    key_locations = [k for k in key_locations if k.get("pos")]

    # ---- cameras and witnesses -----------------------------------------------------------
    observers: List[dict] = []
    raw_obs = [o for o in _as_list(raw.get("observers")) if isinstance(o, dict)][:MAX_OBSERVERS]
    for it in raw_obs:
        oid = take_id(it.get("id"))
        if not oid:
            continue
        kind = "camera" if str(it.get("kind") or "").lower() == "camera" else "witness"
        refs = refs_of(it.get("evidence_refs"))
        eye = CONFIG["camera_eye_m"] if kind == "camera" else CONFIG["witness_eye_m"]
        if normalize_id(it.get("room")) == "outside":
            pt = outside_point(normalize_id(it.get("near")), to_float(it.get("distance_m"), 3.0), to_float(it.get("lateral_m"), 0.0))
            if pt is None:
                continue
            space, level = "outside", 0
        else:
            room = room_by_id[room_of(it.get("room"), "observer", oid)]
            walk = _shrink(_room_rect(room), t2 + 0.1)
            fx_, fz_ = _frac2(it.get("position_frac"))
            pt = [round(walk[0] + fx_ * (walk[1] - walk[0]), 3), 0.0, round(walk[2] + fz_ * (walk[3] - walk[2]), 3)]
            space, level = room["id"], room["level"]
        fov = clamp(to_float(it.get("fov_deg"), 95.0 if kind == "camera" else 140.0) or 95.0, 20.0, 360.0)
        rng = clamp(to_float(it.get("range_m"), 15.0 if kind == "camera" else 25.0) or 15.0, 2.0, 80.0)
        observers.append({"id": oid, "label": clean_text(it.get("label"), 80) or oid, "kind": kind, "room": space, "level": level, "pos": pt,
                          "eye_height_m": eye, "fov_deg": fov, "range_m": rng, "facing_toward": normalize_id(it.get("facing_toward")),
                          "evidence_refs": refs, "basis": _basis(it.get("basis"), refs), "yaw": 0.0})

    layout: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "engine_version": ENGINE_VERSION,
        "wall_thickness_m": CONFIG["wall_thickness_m"], "actor_radius_m": CONFIG["actor_radius_m"], "door_height_m": DOOR_HEIGHT_M,
        "dimensions_basis": dim_basis_overall, "rooms": rooms, "levels": floors, "openings": openings, "fixtures": fixtures,
        "key_locations": key_locations, "outdoor_objects": outdoor_objects, "observers": observers,
        "notes": clean_text(raw.get("notes"), 600), "warnings": warnings, "defaults_used": defaults, "limits": limits,
    }
    # observers face a named place, else the nearest door, else the middle of their room
    node_pos = {n["id"]: (n.get("pos") or n.get("gap_pos")) for n in rooms_as_nodes(layout)}
    for ob in observers:
        tgt = node_pos.get(ob["facing_toward"])
        if tgt is None:
            near = [o for o in openings if ob["room"] in (o["room_a"], o["room_b"])]
            if near:
                tgt = near[0]["gap_pos"]
            elif ob["room"] in room_by_id:
                rr = room_by_id[ob["room"]]["rect"]
                tgt = [(rr[0] + rr[1]) / 2, 0.0, (rr[2] + rr[3]) / 2]
            else:
                tgt = [0.0, 0.0, 0.0]
        ob["yaw"] = round(math.atan2(tgt[0] - ob["pos"][0], tgt[2] - ob["pos"][2]), 4)
    attach_stand_points(layout)
    nodes = all_nodes(layout)
    layout["coverage"] = {b: sum(1 for n in nodes if n.get("basis") == b) for b in ("stated", "inferred", "assumed", "officer")}
    try:
        src = json.dumps(raw, sort_keys=True, default=str)
        layout["source"] = json.loads(src) if len(src) < 90_000 else None
    except (TypeError, ValueError):
        layout["source"] = None
    return layout


def rooms_as_nodes(layout: dict) -> List[dict]:
    out: List[dict] = []
    for r in layout["rooms"]:
        x0, x1, z0, z1 = _room_rect(r)
        out.append({**r, "pos": [(x0 + x1) / 2, 0.0, (z0 + z1) / 2]})
    return out + layout["openings"] + layout["fixtures"] + layout["key_locations"] + layout.get("outdoor_objects", []) + layout.get("observers", [])


def all_nodes(layout: dict) -> List[dict]:
    return layout["rooms"] + layout["openings"] + layout["fixtures"] + layout["key_locations"] + layout.get("outdoor_objects", []) + layout.get("observers", [])


# --------------------------------------------------------------------------
# Navigation grids
# --------------------------------------------------------------------------

class NavGrid:
    """A walkable rectangle with inflated obstacle boxes, rasterised for A*."""

    def __init__(self, walk: Rect, boxes: List[Rect], cell: Optional[float] = None):
        self.walk = walk
        self.boxes = boxes
        span = max(walk[1] - walk[0], walk[3] - walk[2], 1.0)
        self.cell = cell if cell else max(0.1, span / 220.0)
        self.nx = max(1, int((walk[1] - walk[0]) / self.cell) + 1)
        self.nz = max(1, int((walk[3] - walk[2]) / self.cell) + 1)
        self.free = bytearray(b"\x01") * (self.nx * self.nz)
        for b in boxes:
            ix0 = max(0, int(math.floor((b[0] - walk[0]) / self.cell)) - 1)
            ix1 = min(self.nx - 1, int(math.ceil((b[1] - walk[0]) / self.cell)) + 1)
            iz0 = max(0, int(math.floor((b[2] - walk[2]) / self.cell)) - 1)
            iz1 = min(self.nz - 1, int(math.ceil((b[3] - walk[2]) / self.cell)) + 1)
            for iz in range(iz0, iz1 + 1):
                z = walk[2] + iz * self.cell
                if not (b[2] + 1e-7 < z < b[3] - 1e-7):
                    continue
                for ix in range(ix0, ix1 + 1):
                    x = walk[0] + ix * self.cell
                    if b[0] + 1e-7 < x < b[1] - 1e-7:
                        self.free[iz * self.nx + ix] = 0
        self._comp: Optional[List[int]] = None

    def center(self, ix: int, iz: int) -> List[float]:
        return [self.walk[0] + ix * self.cell, 0.0, self.walk[2] + iz * self.cell]

    def cell_of(self, p) -> Tuple[int, int]:
        ix = int(round((p[0] - self.walk[0]) / self.cell))
        iz = int(round((p[2] - self.walk[2]) / self.cell))
        return max(0, min(self.nx - 1, ix)), max(0, min(self.nz - 1, iz))

    def is_free_cell(self, ix: int, iz: int) -> bool:
        return 0 <= ix < self.nx and 0 <= iz < self.nz and bool(self.free[iz * self.nx + ix])

    def point_free(self, p, margin: float = 0.0) -> bool:
        w = _shrink(self.walk, margin)
        return _in_rect(p, w, 1e-9) and not any(_strictly_in_rect(p, _expand(b, margin)) for b in self.boxes)

    def segment_free(self, a, b) -> bool:
        if not (_in_rect(a, self.walk, 1e-9) and _in_rect(b, self.walk, 1e-9)):
            return False
        return not any(_seg_hits_rect(a, b, bx) for bx in self.boxes)

    def nearest_free_cell(self, p, max_r: float = 1.5) -> Optional[Tuple[int, int]]:
        ix, iz = self.cell_of(p)
        if self.is_free_cell(ix, iz):
            return ix, iz
        rmax = int(max_r / self.cell) + 1
        for r in range(1, rmax + 1):
            best, best_d = None, None
            for dz in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dz)) != r:
                        continue
                    if self.is_free_cell(ix + dx, iz + dz):
                        d = dx * dx + dz * dz
                        if best_d is None or d < best_d:
                            best, best_d = (ix + dx, iz + dz), d
            if best is not None:
                return best
        return None

    def components(self) -> List[int]:
        if self._comp is not None:
            return self._comp
        comp = [-1] * (self.nx * self.nz)
        cid = 0
        for start in range(self.nx * self.nz):
            if not self.free[start] or comp[start] != -1:
                continue
            comp[start] = cid
            stack = [start]
            while stack:
                cur = stack.pop()
                cz, cx = divmod(cur, self.nx)
                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx_, nz_ = cx + dx, cz + dz
                    if 0 <= nx_ < self.nx and 0 <= nz_ < self.nz:
                        j = nz_ * self.nx + nx_
                        if self.free[j] and comp[j] == -1:
                            comp[j] = cid
                            stack.append(j)
            cid += 1
        self._comp = comp
        return comp

    def comp_of(self, p, max_r: float = 0.6) -> int:
        c = self.nearest_free_cell(p, max_r)
        return -1 if c is None else self.components()[c[1] * self.nx + c[0]]

    def astar(self, start: Tuple[int, int], goal: Tuple[int, int]) -> Optional[List[Tuple[int, int]]]:
        if start == goal:
            return [start]
        sq2 = math.sqrt(2.0)
        open_h: List[Tuple[float, int, Tuple[int, int]]] = []
        g = {start: 0.0}
        came: Dict[Tuple[int, int], Tuple[int, int]] = {}
        counter = 0

        def h(c):
            dx, dz = abs(c[0] - goal[0]), abs(c[1] - goal[1])
            return max(dx, dz) + (sq2 - 1) * min(dx, dz)

        heapq.heappush(open_h, (h(start), counter, start))
        closed = set()
        while open_h:
            _, _, cur = heapq.heappop(open_h)
            if cur in closed:
                continue
            if cur == goal:
                path = [cur]
                while cur in came:
                    cur = came[cur]
                    path.append(cur)
                return path[::-1]
            closed.add(cur)
            cx, cz = cur
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                nb = (cx + dx, cz + dz)
                if not self.is_free_cell(*nb):
                    continue
                if dx and dz and not (self.is_free_cell(cx + dx, cz) and self.is_free_cell(cx, cz + dz)):
                    continue
                ng = g[cur] + (sq2 if (dx and dz) else 1.0)
                if ng < g.get(nb, 1e18):
                    g[nb] = ng
                    came[nb] = cur
                    counter += 1
                    heapq.heappush(open_h, (ng + h(nb), counter, nb))
        return None

    def endpoint_cell(self, p, max_r: float = 1.0) -> Optional[Tuple[int, int]]:
        """Nearest free cell that the exact point p can reach in a straight, unobstructed hop
        (the nearest free cell alone can sit behind an obstacle corner)."""
        ix, iz = self.cell_of(p)
        rmax = int(max_r / self.cell) + 1
        for r in range(0, rmax + 1):
            best, best_d = None, None
            for dz in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dz)) != r or not self.is_free_cell(ix + dx, iz + dz):
                        continue
                    if not self.segment_free(p, self.center(ix + dx, iz + dz)):
                        continue
                    d = (self.center(ix + dx, iz + dz)[0] - p[0]) ** 2 + (self.center(ix + dx, iz + dz)[2] - p[2]) ** 2
                    if best_d is None or d < best_d:
                        best, best_d = (ix + dx, iz + dz), d
            if best is not None:
                return best
        return self.nearest_free_cell(p, max_r)

    def route(self, a, b) -> Dict[str, Any]:
        if self.segment_free(a, b):
            return {"pts": [list(a), list(b)], "failed": False}
        sa, sb = self.endpoint_cell(a, 1.0), self.endpoint_cell(b, 1.0)
        if sa is None or sb is None:
            return {"pts": [list(a), list(b)], "failed": True}
        cells = self.astar(sa, sb)
        if cells is None:
            return {"pts": [list(a), list(b)], "failed": True}
        pts = [list(a)] + [self.center(ix, iz) for ix, iz in cells] + [list(b)]
        out = [pts[0]]
        i = 0
        while i < len(pts) - 1:
            j = len(pts) - 1
            while j > i + 1 and not self.segment_free(pts[i], pts[j]):
                j -= 1
            out.append(pts[j])
            i = j
        ded = [out[0]]
        for p in out[1:]:
            if _dist(ded[-1], p) > 1e-6:
                ded.append(p)
        if len(ded) == 1:
            ded.append(list(b))
        return {"pts": ded, "failed": False}


# --------------------------------------------------------------------------
# The scene: rooms, outdoor area, doors and stairs as one routable world
# --------------------------------------------------------------------------

class Scene:
    def __init__(self, layout: dict):
        self.layout = layout
        self.t2 = layout["wall_thickness_m"] / 2
        self.R = layout["actor_radius_m"]
        self.rooms = {r["id"]: r for r in layout["rooms"]}
        self.openings = {o["id"]: o for o in layout["openings"]}
        self.fx_by_room: Dict[str, List[dict]] = {}
        for f in layout["fixtures"]:
            self.fx_by_room.setdefault(f["room"], []).append(f)
        self.grids: Dict[str, NavGrid] = {}
        for rid, room in self.rooms.items():
            walk = _shrink(_room_rect(room), self.t2 + self.R)
            boxes = [_expand(_fixture_rect(f), self.R) for f in self.fx_by_room.get(rid, [])]
            self.grids[rid] = NavGrid(walk, boxes)
        ground = [r for r in layout["rooms"] if r["level"] == 0]
        rects = [_room_rect(r) for r in ground] or [(0.0, 1.0, 0.0, 1.0)]
        margin = layout.get("outside_margin", CONFIG["outside_offset_m"] + 8.0)
        self.outside_bounds: Rect = (min(r[0] for r in rects) - margin, max(r[1] for r in rects) + margin,
                                     min(r[2] for r in rects) - margin, max(r[3] for r in rects) + margin)
        self.outer_rects = [_expand(_room_rect(r), self.t2) for r in ground]
        obst = [_expand(o, self.R) for o in self.outer_rects] + [_expand(_fixture_rect(f), self.R) for f in layout.get("outdoor_objects", [])]
        self.outside = NavGrid(self.outside_bounds, obst, cell=max(0.2, (self.outside_bounds[1] - self.outside_bounds[0]) / 260.0))
        self._edge_cache: Dict[Any, Dict[str, Any]] = {}
        self._wall_slabs: Optional[List[Tuple[float, float, float, float, float, float]]] = None

    # ---- helpers -------------------------------------------------------
    def floor_y(self, space: str) -> float:
        r = self.rooms.get(space)
        return r["floor_y"] if r else 0.0

    def grid(self, space: str) -> NavGrid:
        return self.outside if space == "outside" else self.grids[space]

    def level_of_y(self, y: float) -> int:
        return min(self.layout["levels"], key=lambda f: abs(f["floor_y"] - y))["level"]

    def space_path(self, space: str, a, b) -> Dict[str, Any]:
        key = (space, round(a[0], 3), round(a[2], 3), round(b[0], 3), round(b[2], 3))
        hit = self._edge_cache.get(key)
        if hit is None:
            hit = self.grid(space).route(a, b)
            self._edge_cache[key] = hit
        return hit

    def _side_points(self, op: dict) -> List[Tuple[str, List[float]]]:
        if op["kind"] == "external":
            return [(op["room_a"], op["pos_a"]), ("outside", op["outside_pos"])]
        return [(op["room_a"], op["pos_a"]), (op["room_b"], op["pos_b"])]

    def opening_usable(self, op: dict) -> bool:
        if not op.get("passable", True):
            return False
        for space, p in self._side_points(op):
            if op["kind"] == "stairs":
                if not self.grid(space).point_free(p, 0.0):
                    return False
            elif not self.grid(space).point_free(p):
                return False
        return True

    # ---- routing --------------------------------------------------------
    def route(self, A: dict, B: dict) -> Dict[str, Any]:
        """Shortest walkable route between two locations through rooms, doors,
        stairs and the outdoor area.

        A location is {"space": room id | "outside", "pos": [x,0,z]} or
        {"gap": opening} (standing in a doorway). Returns 3-D points, per-leg
        kind / opening / speed factor / true length, and the doorways passed."""
        stair_slow = CONFIG["stairs_speed_factor"]
        slope = math.sin(math.radians(CONFIG["stairs_slope_deg"]))
        nodes: Dict[Any, Tuple[Optional[str], List[float]]] = {}
        gap_op: Dict[Any, dict] = {}
        for nid, loc in (("S", A), ("E", B)):
            if "gap" in loc:
                nodes[nid] = (None, loc["gap"]["gap_pos"])
                gap_op[nid] = loc["gap"]
            else:
                nodes[nid] = (loc["space"], loc["pos"])
        same_gap = "S" in gap_op and "E" in gap_op and gap_op["S"]["id"] == gap_op["E"]["id"]
        same_spot = (nodes["S"][0] == nodes["E"][0] and nodes["S"][0] is not None and _dist(nodes["S"][1], nodes["E"][1]) < 1e-9)
        if same_gap or same_spot:
            sp, p = nodes["S"]
            y = self.floor_y(sp) if sp else self.floor_y(gap_op["S"]["room_a"])
            return {"failed": False, "pts": [[p[0], y, p[2]]], "leg_kinds": [], "leg_openings": [], "leg_factors": [], "leg_lengths": [],
                    "crossings": [], "length_m": 0.0, "eff_length_m": 0.0}
        for op in self.openings.values():
            if self.opening_usable(op):
                for i, (sp, p) in enumerate(self._side_points(op)):
                    nodes[("op", op["id"], i)] = (sp, p)
        by_space: Dict[str, List[Any]] = {}
        for nid, (sp, _) in nodes.items():
            if sp is not None:
                by_space.setdefault(sp, []).append(nid)

        def y_of(space: Optional[str]) -> float:
            return 0.0 if space in (None, "outside") else self.floor_y(space)

        def door_edge(op: dict, pts: List[List[float]], extra: float = 0.0) -> dict:
            length = _polyline_len(pts)
            return {"kind": "door", "opening": op["id"], "pts": pts, "factor": 1.0, "len": length, "cost": length + extra}

        def neighbors(nid):
            sp, pos = nodes[nid]
            if nid in gap_op:
                op = gap_op[nid]
                yo = self.floor_y(op["room_a"])
                for i, (_, p2) in enumerate(self._side_points(op)):
                    oid = ("op", op["id"], i)
                    if oid in nodes:
                        yield oid, door_edge(op, [[pos[0], yo, pos[2]], [p2[0], yo, p2[2]]])
                return
            if isinstance(nid, tuple):
                op = self.openings[nid[1]]
                i = nid[2]
                sides = self._side_points(op)
                (sp_i, p_i), (sp_j, p_j) = sides[i], sides[1 - i]
                oth = ("op", op["id"], 1 - i)
                if oth in nodes:
                    if op["kind"] == "stairs":
                        ya, yb = y_of(sp_i), y_of(sp_j)
                        length = math.hypot(_dist(p_i, p_j), abs(yb - ya) / slope)
                        yield oth, {"kind": "stairs", "opening": op["id"], "pts": [[p_i[0], ya, p_i[2]], [p_j[0], yb, p_j[2]]],
                                    "factor": 1.0 / stair_slow, "len": length, "cost": length / stair_slow}
                    else:
                        yo = self.floor_y(op["room_a"])
                        pen = 25.0 if op["state"] == "locked" else 2.0 if op["state"] == "intact" else 0.0
                        yield oth, door_edge(op, [[p_i[0], yo, p_i[2]], [op["gap_pos"][0], yo, op["gap_pos"][2]], [p_j[0], yo, p_j[2]]], pen)
                for gid, gop in gap_op.items():
                    if gop["id"] == op["id"]:
                        yo = self.floor_y(op["room_a"])
                        yield gid, door_edge(op, [[p_i[0], yo, p_i[2]], [gop["gap_pos"][0], yo, gop["gap_pos"][2]]])
            if sp is not None:
                for other in by_space.get(sp, []):
                    if other == nid:
                        continue
                    res = self.space_path(sp, pos, nodes[other][1])
                    if res["failed"]:
                        continue
                    pts = [[q[0], y_of(sp), q[2]] for q in res["pts"]]
                    length = _polyline_len(pts)
                    yield other, {"kind": "walk", "space": sp, "pts": pts, "factor": 1.0, "len": length, "cost": length}

        dist: Dict[Any, float] = {"S": 0.0}
        prev: Dict[Any, Tuple[Any, dict]] = {}
        heap: List[Tuple[float, int, Any]] = [(0.0, 0, "S")]
        counter = 0
        done = set()
        while heap:
            d, _, cur = heapq.heappop(heap)
            if cur in done:
                continue
            if cur == "E":
                break
            done.add(cur)
            for nb, e in neighbors(cur):
                nd = d + e["cost"]
                if nd < dist.get(nb, 1e18) - 1e-9:
                    dist[nb] = nd
                    prev[nb] = (cur, e)
                    counter += 1
                    heapq.heappush(heap, (nd, counter, nb))
        if "E" not in prev:
            return {"failed": True, "pts": [], "leg_kinds": [], "leg_openings": [], "leg_factors": [], "leg_lengths": [], "crossings": [],
                    "length_m": 0.0, "eff_length_m": 0.0}
        chain: List[dict] = []
        cur = "E"
        while cur != "S":
            pv, e = prev[cur]
            chain.append(e)
            cur = pv
        chain.reverse()
        pts: List[List[float]] = []
        kinds: List[str] = []
        ops: List[Optional[str]] = []
        factors: List[float] = []
        lengths: List[float] = []
        crossings: List[Dict[str, Any]] = []
        for e in chain:
            gp = self.openings[e["opening"]]["gap_pos"] if e["kind"] == "door" else None
            for q in e["pts"]:
                same = pts and abs(pts[-1][0] - q[0]) < 1e-9 and abs(pts[-1][2] - q[2]) < 1e-9 and abs(pts[-1][1] - q[1]) < 1e-9
                if not same:
                    if pts:
                        kinds.append(e["kind"])
                        ops.append(e.get("opening"))
                        factors.append(e["factor"])
                        lengths.append(e["len"] if e["kind"] == "stairs" else _dist(pts[-1], q))
                    pts.append([q[0], q[1], q[2]])
                if gp is not None and abs(q[0] - gp[0]) < 1e-9 and abs(q[2] - gp[2]) < 1e-9:
                    crossings.append({"opening": e["opening"], "index": len(pts) - 1})
        length = sum(lengths)
        eff = sum(l_ * f_ for l_, f_ in zip(lengths, factors))
        return {"failed": False, "pts": pts, "leg_kinds": kinds, "leg_openings": ops, "leg_factors": factors, "leg_lengths": lengths,
                "crossings": crossings, "length_m": length, "eff_length_m": eff}

    # ---- visibility -----------------------------------------------------
    def wall_slabs(self) -> List[Tuple[float, float, float, float, float, float]]:
        """(x1, z1, x2, z2, y_lo, y_hi): vertical slabs that block a line of sight.
        Walls with door gaps cut out, a lintel left above each gap."""
        if self._wall_slabs is not None:
            return self._wall_slabs
        slabs: List[Tuple[float, float, float, float, float, float]] = []
        by_line: Dict[Tuple[str, float, int], List[dict]] = {}
        for op in self.openings.values():
            if op["kind"] != "stairs":
                by_line.setdefault((op["orient"], round(op["line"], 3), op["level"]), []).append(op)
        seen = set()
        for room in self.rooms.values():
            fy, h = room["floor_y"], room["height_m"]
            for wall in SIDES:
                orient, line, e0, e1 = _edge_of(room, wall)
                key = (orient, round(line, 3), room["level"], round(e0, 3), round(e1, 3))
                if key in seen:
                    continue
                seen.add(key)
                gaps = sorted((o["gap_center_m"] - o["width_m"] / 2, o["gap_center_m"] + o["width_m"] / 2) for o in by_line.get((orient, round(line, 3), room["level"]), [])
                              if e0 - 1e-6 <= o["gap_center_m"] <= e1 + 1e-6)
                cur = e0
                for lo, hi in gaps:
                    if lo > cur:
                        slabs.append(self._slab(orient, line, cur, lo, fy, fy + h))
                    slabs.append(self._slab(orient, line, lo, hi, fy + DOOR_HEIGHT_M, fy + h))
                    cur = max(cur, hi)
                if cur < e1:
                    slabs.append(self._slab(orient, line, cur, e1, fy, fy + h))
        self._wall_slabs = slabs
        return slabs

    @staticmethod
    def _slab(orient: str, line: float, a: float, b: float, y0: float, y1: float):
        return (line, a, line, b, y0, y1) if orient == "z" else (a, line, b, line, y0, y1)

    def visible(self, obs: dict, target, target_y: float, target_h: float = 1.2) -> Tuple[bool, str]:
        ox, oz = obs["pos"][0], obs["pos"][2]
        oy = self.floor_y(obs["room"]) + obs["eye_height_m"]
        dx, dz = target[0] - ox, target[2] - oz
        dist = math.hypot(dx, dz)
        if dist > obs["range_m"]:
            return False, f"{dist:.1f} m away, beyond its {obs['range_m']:.0f} m range"
        if dist > 1e-6:
            diff = (math.atan2(dx, dz) - obs["yaw"] + math.pi * 3) % (math.tau) - math.pi
            if abs(diff) > math.radians(obs["fov_deg"]) / 2 + 1e-9:
                return False, "outside its field of view"
        if obs["room"] != "outside" and obs["level"] != self.level_of_y(target_y):
            return False, "is on a different floor"
        if obs["room"] == "outside" and self.level_of_y(target_y) != 0:
            return False, "cannot see an upper floor from outside"
        ty = target_y + target_h

        def ray_y(t: float) -> float:
            return oy + (ty - oy) * t

        for (x1, z1, x2, z2, y0, y1) in self.wall_slabs():
            t = _seg_param_hit(ox, oz, dx, dz, x1, z1, x2, z2)
            if t is not None and 1e-6 < t < 1 - 1e-6 and y0 - 1e-6 <= ray_y(t) <= y1 + 1e-6:
                return False, "a wall blocks the view"
        for f in list(self.layout["fixtures"]) + list(self.layout.get("outdoor_objects", [])):
            fy = self.floor_y(f["room"])
            if abs(fy - target_y) > 1.0 and f["room"] != "outside":
                continue
            r = _fixture_rect(f)
            tt = _seg_rect_params(ox, oz, dx, dz, r)
            if tt is not None:
                mid = (tt[0] + tt[1]) / 2
                if 1e-6 < mid < 1 - 1e-6 and ray_y(mid) <= fy + f["height_m"]:
                    return False, f"'{f['label']}' blocks the view"
        return True, "clear line of sight"


def _seg_param_hit(ox, oz, dx, dz, x1, z1, x2, z2) -> Optional[float]:
    ex, ez = x2 - x1, z2 - z1
    den = dx * ez - dz * ex
    if abs(den) < 1e-12:
        return None
    t = ((x1 - ox) * ez - (z1 - oz) * ex) / den
    u = ((x1 - ox) * dz - (z1 - oz) * dx) / den
    return t if 0.0 <= u <= 1.0 else None


def _seg_rect_params(ox, oz, dx, dz, r: Rect) -> Optional[Tuple[float, float]]:
    t0, t1 = 0.0, 1.0
    for p, q, lo, hi in ((dx, ox, r[0], r[1]), (dz, oz, r[2], r[3])):
        if abs(p) < 1e-12:
            if q < lo or q > hi:
                return None
        else:
            ta, tb = (lo - q) / p, (hi - q) / p
            if ta > tb:
                ta, tb = tb, ta
            t0, t1 = max(t0, ta), min(t1, tb)
            if t0 > t1:
                return None
    return (t0, t1)


_SCENE_CACHE: Dict[str, Scene] = {}


def get_scene(layout: dict) -> Scene:
    key = json.dumps(layout, sort_keys=True, default=str)
    sc = _SCENE_CACHE.get(key)
    if sc is None:
        if len(_SCENE_CACHE) >= 6:
            _SCENE_CACHE.pop(next(iter(_SCENE_CACHE)))
        sc = Scene(layout)
        _SCENE_CACHE[key] = sc
    return sc


# --------------------------------------------------------------------------
# Stand points and reachability
# --------------------------------------------------------------------------

def attach_stand_points(layout: dict) -> None:
    """Gives every place a walkable `stand_pos`, a `face_pos`, and whether it
    can be reached from outside the building. A fixture, or a key location
    sitting inside a fixture, is never a place a person can stand; they stand
    beside it."""
    sc = Scene(layout)
    R = sc.R
    # connected pieces of floor, and which of them connect to the outside
    parent: Dict[Any, Any] = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    union("OUT", "OUT")
    for op in sc.openings.values():
        if not sc.opening_usable(op):
            continue
        sides = sc._side_points(op)
        nodes_ = [(space, sc.grid(space).comp_of(p)) for space, p in sides]
        if any(c < 0 for _, c in nodes_):
            continue
        if op["kind"] == "external":
            union(nodes_[0], "OUT")
        else:
            union(nodes_[0], nodes_[1])

    def accessible(space: str, p) -> bool:
        c = sc.grid(space).comp_of(p, 0.6)
        if c < 0:
            return False
        if space == "outside":
            return True
        return find((space, c)) == find("OUT")

    def fixture_stand(fx: dict, space: str, toward) -> Optional[List[float]]:
        grid = sc.grid(space)
        hw, hd = fx["footprint_m"][0] / 2 + R + 0.05, fx["footprint_m"][1] / 2 + R + 0.05
        cx, cz = fx["pos"][0], fx["pos"][2]
        cands = []
        for k in (-1, -0.5, 0, 0.5, 1):
            cands += [[cx + k * hw, 0.0, cz + hd], [cx + k * hw, 0.0, cz - hd], [cx + hw, 0.0, cz + k * hd], [cx - hw, 0.0, cz + k * hd]]
        good = [c for c in cands if grid.point_free(c, STAND_MARGIN_M) and accessible(space, c)] or [c for c in cands if grid.point_free(c, STAND_MARGIN_M)]
        if not good:
            return None
        good.sort(key=lambda c: _dist(c, toward))
        return [round(good[0][0], 3), 0.0, round(good[0][2], 3)]

    def toward_for(space: str, pos) -> List[float]:
        pts = [p for sp, p in [s for o in sc.openings.values() for s in sc._side_points(o)] if sp == space]
        return min(pts, key=lambda p: _dist(p, pos)) if pts else pos

    for op in layout["openings"]:
        op["stand_pos"] = list(op["pos_a"])
        op["face_pos"] = None
        op["reachable"] = bool(sc.opening_usable(op)) and accessible(op["room_a"], op["pos_a"])
    for room in layout["rooms"]:
        grid = sc.grids[room["id"]]
        cx, cz = (room["rect"][0] + room["rect"][1]) / 2, (room["rect"][2] + room["rect"][3]) / 2
        p = [cx, 0.0, cz]
        if not grid.point_free(p, STAND_MARGIN_M):
            c = grid.nearest_free_cell(p, 3.0)
            if c:
                p = grid.center(*c)
        room["stand_pos"] = [round(p[0], 3), 0.0, round(p[2], 3)]
        room["face_pos"] = None
        room["pos"] = [round(cx, 3), 0.0, round(cz, 3)]
        room["reachable"] = accessible(room["id"], p)
    for fx in layout["fixtures"]:
        sp = fixture_stand(fx, fx["room"], toward_for(fx["room"], fx["pos"]))
        fx["stand_pos"] = sp if sp else list(fx["pos"])
        fx["face_pos"] = list(fx["pos"])
        fx["reachable"] = bool(sp and accessible(fx["room"], sp))
    for ob in layout.get("outdoor_objects", []):
        sp = fixture_stand(ob, "outside", ob["pos"])
        ob["stand_pos"] = sp if sp else list(ob["pos"])
        ob["face_pos"] = list(ob["pos"])
        ob["reachable"] = bool(sp)
    fixtures_by_room: Dict[str, List[Tuple[dict, Rect]]] = {}
    for fx in layout["fixtures"]:
        fixtures_by_room.setdefault(fx["room"], []).append((fx, _expand(_fixture_rect(fx), R)))
    for kl in layout["key_locations"]:
        space = kl["room"]
        grid = sc.grid(space)
        host = None
        if space != "outside":
            for fx, box in fixtures_by_room.get(space, []):
                if _strictly_in_rect(kl["pos"], box, 1e-9):
                    host = fx
                    break
        else:
            for ob in layout.get("outdoor_objects", []):
                if _strictly_in_rect(kl["pos"], _expand(_fixture_rect(ob), R), 1e-9):
                    host = ob
                    break
        if host is not None:
            sp = fixture_stand(host, space, kl["pos"])
            kl["on_fixture"] = host["id"]
            kl["stand_pos"] = sp if sp else list(kl["pos"])
            kl["face_pos"] = list(kl["pos"])
            kl["reachable"] = bool(sp and accessible(space, sp))
        else:
            p = list(kl["pos"])
            if not grid.point_free(p, STAND_MARGIN_M):
                c = grid.nearest_free_cell(p, 1.5)
                if c:
                    p = grid.center(*c)
            kl["on_fixture"] = None
            kl["stand_pos"] = [round(p[0], 3), 0.0, round(p[2], 3)]
            kl["face_pos"] = None
            kl["reachable"] = accessible(space, p)
    for ob in layout.get("observers", []):
        grid = sc.grid(ob["room"])
        p = list(ob["pos"])
        if not grid.point_free(p, STAND_MARGIN_M):
            c = grid.nearest_free_cell(p, 2.0)
            if c:
                p = grid.center(*c)
        ob["stand_pos"] = [round(p[0], 3), 0.0, round(p[2], 3)]
        ob["face_pos"] = None
        ob["reachable"] = grid.point_free(p, STAND_MARGIN_M) and accessible(ob["room"], p)
    unreachable = [n["id"] for n in layout["rooms"] + layout["openings"] + layout["fixtures"] + layout["key_locations"] if not n["reachable"]]
    if unreachable:
        layout["warnings"].append("not reachable from outside the building (blocked by furniture, walls or a locked-off area): " + ", ".join(unreachable))


# --------------------------------------------------------------------------
# Timing
# --------------------------------------------------------------------------

def _loc_y(sc: "Scene", loc: dict) -> float:
    if "gap" in loc:
        return sc.floor_y(loc["gap"]["room_a"])
    return 0.0 if loc["space"] == "outside" else sc.floor_y(loc["space"])


def _time_at_distance(d: float, total: float, v: float, a: float) -> float:
    """Seconds after starting at which a walker following transit_seconds() has covered d metres."""
    d = clamp(d, 0.0, total)
    d_acc = v * v / (2 * a)
    if total >= 2 * d_acc:
        if d <= d_acc:
            return math.sqrt(2 * d / a)
        if d <= total - d_acc:
            return v / a + (d - d_acc) / v
        return transit_seconds(total, v, a) - math.sqrt(max(0.0, 2 * (total - d) / a))
    half = total / 2
    if d <= half:
        return math.sqrt(2 * d / a)
    return transit_seconds(total, v, a) - math.sqrt(max(0.0, 2 * (total - d) / a))


def transit_seconds(eff_len: float, v: float, a: float) -> float:
    """Time to walk eff_len metres: accelerate, cruise, brake (trapezoid profile)."""
    if eff_len <= 1e-9:
        return 0.0
    d_acc = v * v / (2 * a)
    if eff_len >= 2 * d_acc:
        return eff_len / v + v / a
    return 2 * math.sqrt(eff_len / a)


# --------------------------------------------------------------------------
# Scenario planning (any number of people)
# --------------------------------------------------------------------------

def _parse_actors(raw_actors: Any, warnings: List[str]) -> List[dict]:
    actors: List[dict] = []
    used: set = set()
    for it in _as_list(raw_actors)[:MAX_ACTORS]:
        if not isinstance(it, dict):
            continue
        aid = normalize_id(it.get("id"))
        if not aid or aid in used:
            continue
        used.add(aid)
        refs = [str(r) for r in _as_list(it.get("evidence_refs"))][:8]
        actors.append({
            "id": aid, "label": clean_text(it.get("label"), 60) or aid, "role": clean_text(it.get("role"), 24).lower() or "person",
            "color": ACTOR_COLORS[len(actors) % len(ACTOR_COLORS)], "evidence_refs": refs,
            "start_offset_s": clamp(to_seconds(it.get("start_offset_s"), 0.0), 0.0, 7200.0),
        })
    if len(_as_list(raw_actors)) > MAX_ACTORS:
        warnings.append(f"only the first {MAX_ACTORS} people are modelled")
    if not actors:
        actors.append({"id": "person_1", "label": "Person 1", "role": "person", "color": ACTOR_COLORS[0], "evidence_refs": [], "start_offset_s": 0.0})
    return actors


def plan_scenario(steps: Any, layout: dict, actors: Any = None) -> Dict[str, Any]:
    """Turns step lists (one flat list; each step may name its `actor`) into a
    timed, routed plan for every person. Steps reference places by id only;
    unknown ids are dropped and reported, never invented. Each step becomes a
    walk followed by time spent doing the action, so actions never happen
    while walking."""
    sc = get_scene(layout)
    result: Dict[str, Any] = {
        "ok": False, "actors": [], "violations": [], "warnings": [], "time_adjustments": [], "dropped_steps": [], "route_notes": [],
        "doors_used": [], "effects": [], "observation_claims": [], "total_duration_s": 0.0, "total_distance_m": 0.0,
    }
    actor_list = _parse_actors(actors, result["warnings"])
    actor_ids = [a["id"] for a in actor_list]

    nodes: Dict[str, Tuple[str, dict]] = {}
    for r in layout["rooms"]:
        nodes[r["id"]] = ("room", r)
    for op in layout["openings"]:
        nodes[op["id"]] = ("opening", op)
    for kl in layout["key_locations"]:
        nodes.setdefault(kl["id"], ("key", kl))
    for fx in layout["fixtures"]:
        nodes.setdefault(fx["id"], ("fixture", fx))
    for ob in layout.get("outdoor_objects", []):
        nodes.setdefault(ob["id"], ("outdoor", ob))
    for ob in layout.get("observers", []):
        nodes.setdefault(ob["id"], ("observer", ob))
    observer_ids = {o["id"] for o in layout.get("observers", [])}

    per_actor: Dict[str, List[dict]] = {a["id"]: [] for a in actor_list}
    raw_steps = steps if isinstance(steps, list) else []
    for idx, raw in enumerate(raw_steps[: MAX_STEPS * len(actor_list)]):
        if not isinstance(raw, dict):
            result["dropped_steps"].append({"index": idx, "node_id": "", "reason": "step was not an object"})
            continue
        aid = normalize_id(raw.get("actor")) or actor_ids[0]
        if aid not in per_actor:
            result["dropped_steps"].append({"index": idx, "node_id": clean_text(raw.get("node_id"), 60), "reason": f"person '{aid}' is not listed in the scenario"})
            continue
        if len(per_actor[aid]) >= MAX_STEPS:
            result["dropped_steps"].append({"index": idx, "node_id": "", "reason": f"more than {MAX_STEPS} steps for one person; the rest were not simulated"})
            continue
        nid = normalize_id(raw.get("node_id"))
        if nid == "exterior" or nid == "outside":
            kind, node = "ext", None
        elif nid in nodes:
            kind, node = nodes[nid]
        else:
            result["dropped_steps"].append({"index": idx, "node_id": clean_text(raw.get("node_id"), 60), "reason": "location is not part of the scene layout"})
            continue
        action = normalize_id(raw.get("action"))
        action = action if action in ACTIONS else "other"
        refs = [str(r) for r in _as_list(raw.get("evidence_refs"))]
        effects = []
        for e in _as_list(raw.get("effects"))[:4]:
            if isinstance(e, dict):
                tgt, st = normalize_id(e.get("target")), str(e.get("state") or "").lower()
                if tgt in nodes and nodes[tgt][0] in ("opening", "fixture", "outdoor") and st in EFFECT_STATES:
                    effects.append({"target": tgt, "state": st})
        per_actor[aid].append({
            "src_index": idx, "kind": kind, "node": node, "node_id": "exterior" if kind == "ext" else node["id"], "action": action,
            "claimed_s": clamp(to_seconds(raw.get("dt_sec_estimate"), 30.0), 1.0, 900.0), "narrative": clean_text(raw.get("narrative"), 400),
            "phase": clean_text(raw.get("phase"), 40) or action.upper(), "evidence_refs": refs, "effects": effects,
            "observed_by": [o for o in (normalize_id(x) for x in _as_list(raw.get("observed_by"))) if o in observer_ids][:4],
            "item": clean_text(raw.get("item"), 60), "basis": "evidence" if refs else "inferred",
        })
    if sum(len(v) for v in per_actor.values()) < 2:
        result["violations"].append({"code": "too_few_steps", "step": None, "actor": None, "message": "fewer than two usable steps remained after checking locations against the scene layout"})
        return result
    result["ok"] = True

    externals = [o for o in layout["openings"] if o["kind"] == "external"]
    doors_used: Dict[str, dict] = {}
    all_passes: List[Dict[str, Any]] = []
    unlock_times: Dict[str, float] = {}

    def door_rank(op: dict, cost: float, entering: bool):
        usable = op.get("passable", True) and op.get("reachable", True)
        return (not usable, op["state"] in ("intact", "locked"), 0 if (entering and op["state"] == "forced") else 1, cost)

    def loc_of(s: dict) -> dict:
        if s["kind"] == "ext":
            d = s["door"]
            return {"space": "outside", "pos": d["outside_pos"], "face": d["gap_pos"], "door": d}
        n = s["node"]
        if s["kind"] == "opening":
            if n["kind"] == "stairs":  # a spot on the floor of the upper-listed room; the stairs edge does the climbing
                return {"space": n["room_a"], "pos": n["pos_a"], "face": None, "door": None}
            return {"gap": n, "pos": n["gap_pos"], "face": None, "door": n}
        if s["kind"] == "room":
            return {"space": n["id"], "pos": n["stand_pos"], "face": None, "door": None}
        if s["kind"] in ("fixture", "key"):
            return {"space": n["room"], "pos": n["stand_pos"], "face": n.get("face_pos"), "door": None}
        if s["kind"] == "outdoor":
            return {"space": "outside", "pos": n["stand_pos"], "face": n.get("face_pos"), "door": None}
        return {"space": n["room"], "pos": n["stand_pos"], "face": None, "door": None}  # observer

    actors_out: List[dict] = []
    for actor in actor_list:
        seq = per_actor[actor["id"]]
        if not seq:
            continue
        n = len(seq)
        for i, s in enumerate(seq):
            if s["kind"] != "ext":
                continue
            door, inferred, why = None, False, ""
            for j in (i + 1, i - 1):
                if 0 <= j < n and seq[j]["kind"] == "opening" and seq[j]["node"]["kind"] == "external":
                    door, why = seq[j]["node"], "the adjacent step uses this door"
                    break
            if door is None:
                entering = i + 1 < n and seq[i + 1]["kind"] != "ext"
                ref = seq[i + 1] if entering else (seq[i - 1] if i > 0 else None)
                target = loc_of({**ref, "door": None}) if ref is not None and ref["kind"] != "ext" else None
                best, best_rank = None, None
                for op in externals:
                    cost = 0.0
                    if target is not None:
                        r = sc.route({"space": "outside", "pos": op["outside_pos"]}, target)
                        cost = 1e6 if r["failed"] else r["length_m"]
                    rk = door_rank(op, cost, entering)
                    if best_rank is None or rk < best_rank:
                        best, best_rank = op, rk
                door = best
                inferred = True
                why = "chosen by the system: the scenario did not name a door"
                if door is not None and door["state"] == "forced":
                    why += " (recorded as forced in evidence)"
            if door is None:
                result["violations"].append({"code": "no_route", "step": i, "actor": actor["id"], "message": "there is no outside door, so nobody can arrive from or leave to the outside"})
                door = externals[0] if externals else None
            s["door"], s["door_inferred"], s["door_why"] = door, inferred, why
        segs: List[dict] = []
        steps_out: List[dict] = []
        t = actor["start_offset_s"]
        carrying = False
        prev_loc: Optional[dict] = None
        notes_seen: set = set()
        for k, s in enumerate(seq):
            if s["kind"] == "ext" and s.get("door") is None:
                continue
            lc = loc_of(s)
            node = s["node"]
            label = "Outside the building" if s["kind"] == "ext" else node["label"]
            if s["kind"] != "ext" and not node.get("reachable", True):
                result["violations"].append({"code": "unreachable", "step": k, "actor": actor["id"], "message": f"'{label}' cannot be reached from outside (blocked by furniture, walls or a locked-off area)"})
            used_door = lc.get("door")
            if used_door is not None:
                doors_used.setdefault(used_door["id"], {"id": used_door["id"], "label": used_door["label"], "state": used_door["state"],
                                                         "first_step": k, "actor": actor["id"], "chosen_by_system": bool(s.get("door_inferred"))})
                if not used_door.get("passable", True):
                    result["violations"].append({"code": "door_too_narrow", "step": k, "actor": actor["id"], "message": f"'{used_door['label']}' is too narrow for a person to pass"})
            rid = node["id"] if s["kind"] == "room" else (node.get("room") if s["kind"] in ("fixture", "key", "observer") else None)
            if rid in sc.rooms and not sc.rooms[rid].get("observed", True) and rid not in notes_seen:
                notes_seen.add(rid)
                result["warnings"].append(f"{actor['label']} goes into '{sc.rooms[rid]['label']}', which the evidence does not describe")
            transit_s, route_len, step_notes, auto_routed = 0.0, 0.0, [], False
            arrive = t
            if prev_loc is not None:
                r = sc.route(prev_loc, lc)
                if r["failed"]:
                    result["violations"].append({"code": "no_route", "step": k, "actor": actor["id"], "message": f"no walkable route exists from the previous place to '{label}'"})
                    pts = [[prev_loc["pos"][0], _loc_y(sc, prev_loc), prev_loc["pos"][2]], [lc["pos"][0], _loc_y(sc, lc), lc["pos"][2]]]
                    r = {"pts": pts, "leg_kinds": ["walk"], "leg_openings": [None], "leg_factors": [1.0], "leg_lengths": [_dist(pts[0], pts[1])],
                         "crossings": [], "length_m": _dist(pts[0], pts[1]), "eff_length_m": _dist(pts[0], pts[1])}
                    failed = True
                else:
                    failed = False
                running = s["action"] == "flee"
                v = (CONFIG["run_speed_mps"] if running else CONFIG["walk_speed_mps"]) * (CONFIG["carry_speed_factor"] if carrying and not running else 1.0)
                eff = r["eff_length_m"]
                route_len = r["length_m"]
                transit_s = transit_seconds(eff, v, CONFIG["accel_mps2"])
                step_notes = []
                crossed = [c["opening"] for c in r["crossings"]]
                if any(k_ == "stairs" for k_ in r["leg_kinds"]):
                    step_notes.append("uses the stairs")
                if "outside" in (prev_loc.get("space"), lc.get("space")) or any(sc.openings[c]["kind"] == "external" for c in crossed):
                    for c in crossed:
                        op = sc.openings[c]
                        if op["kind"] == "external":
                            step_notes.append(f"through {op['label']}")
                            break
                inter = [sc.openings[c]["label"] for c in crossed if sc.openings[c]["kind"] == "door"]
                if inter:
                    step_notes.append("through " + ", ".join(inter))
                if s["kind"] == "ext" and s.get("door_inferred"):
                    step_notes.append(f"{s['door']['label']}: {s['door_why']}")
                if len(r["pts"]) > 2 and all(kk == "walk" for kk in r["leg_kinds"]):
                    step_notes.append("path bends to stay clear of walls and furniture")
                auto_routed = bool(step_notes)
                passes = []
                if r["crossings"]:
                    cum = [0.0]
                    for ll, ff in zip(r["leg_lengths"], r["leg_factors"]):
                        cum.append(cum[-1] + ll * ff)
                    for c in r["crossings"]:
                        tc = _time_at_distance(cum[min(c["index"], len(cum) - 1)], eff, v, CONFIG["accel_mps2"])
                        passes.append({"opening": c["opening"], "t": round(t + tc, 3), "actor": actor["id"]})
                        all_passes.append(passes[-1])
                if transit_s > 0:
                    segs.append({
                        "kind": "transit", "actor": actor["id"], "t0": round(t, 3), "t1": round(t + transit_s, 3), "step": k,
                        "node_id": s["node_id"], "label": label, "action": "flee" if running else "move", "phase": "TRANSIT", "narrative": "",
                        "route": [[round(x, 4), round(y, 4), round(z, 4)] for x, y, z in r["pts"]], "leg_kinds": r["leg_kinds"],
                        "leg_openings": r["leg_openings"], "leg_factors": [round(f, 4) for f in r["leg_factors"]],
                        "leg_lengths": [round(x, 4) for x in r["leg_lengths"]], "length_m": round(route_len, 3),
                        "eff_length_m": round(eff, 3), "v_max": round(v, 3), "accel": CONFIG["accel_mps2"], "auto_routed": auto_routed,
                        "routing_notes": step_notes, "carrying": carrying, "item": "", "evidence_refs": [], "face_pos": None, "failed": failed,
                        "passes": passes, "space": prev_loc.get("space") or "",
                    })
                t += transit_s
                arrive = t
            dwell_min = DWELL_MIN_S[s["action"]]
            if prev_loc is None:
                dwell = max(dwell_min, min(s["claimed_s"], 10.0))
            else:
                dwell = max(dwell_min, s["claimed_s"])
                if s["claimed_s"] < dwell_min - 1e-6:
                    result["time_adjustments"].append({"step": k, "actor": actor["id"], "claimed_s": round(s["claimed_s"], 1), "modelled_s": round(dwell, 1),
                                                       "reason": f"'{s['action']}' needs at least {dwell_min:.0f} s on site"})
            dwell = min(dwell, 900.0)
            if s["action"] == "take_item":
                carrying = True
            elif s["action"] in ("drop_item", "hand_over"):
                carrying = False
            space = lc.get("space") or (lc["door"]["room_a"] if lc.get("door") else "outside")
            py = sc.floor_y(space) if space != "outside" else 0.0
            segs.append({
                "kind": "dwell", "actor": actor["id"], "t0": round(t, 3), "t1": round(t + dwell, 3), "step": k, "node_id": s["node_id"], "label": label,
                "action": s["action"], "phase": s["phase"], "narrative": s["narrative"], "pos": [round(lc["pos"][0], 3), round(py, 3), round(lc["pos"][2], 3)],
                "face_pos": [round(x, 3) for x in lc["face"]] if lc.get("face") else None, "auto_routed": False, "routing_notes": [],
                "carrying": carrying, "item": s["item"], "evidence_refs": s["evidence_refs"], "failed": False, "space": space,
            })
            for e in s["effects"]:
                result["effects"].append({"t": round(t + min(dwell / 2, 3.0), 3), "target": e["target"], "state": e["state"], "actor": actor["id"],
                                          "step": k, "cited": bool(s["evidence_refs"])})
                if e["state"] in ("forced", "opened", "unlocked") and e["target"] in sc.openings:
                    unlock_times[e["target"]] = min(unlock_times.get(e["target"], 1e18), t)
            if s["action"] in UNLOCKING_ACTIONS and s["kind"] == "opening":
                unlock_times[s["node_id"]] = min(unlock_times.get(s["node_id"], 1e18), t)
            if s["observed_by"]:
                result["observation_claims"].append({"actor": actor["id"], "step": k, "observers": s["observed_by"], "t0": round(t, 3), "t1": round(t + dwell, 3),
                                                     "pos": [lc["pos"][0], py, lc["pos"][2]], "label": label})
            steps_out.append({
                "k": k, "src_index": s["src_index"], "actor": actor["id"], "node_id": s["node_id"], "label": label, "action": s["action"], "phase": s["phase"],
                "narrative": s["narrative"], "evidence_refs": s["evidence_refs"], "basis": s["basis"], "claimed_s": round(s["claimed_s"], 1),
                "arrive_s": round(arrive, 3), "depart_s": round(t + dwell, 3), "route_notes": step_notes, "auto_routed": auto_routed, "item": s["item"],
                "effects": s["effects"], "observed_by": s["observed_by"],
            })
            t += dwell
            prev_loc = lc
        if segs:
            actors_out.append({**actor, "segments": segs, "steps": steps_out, "end_s": round(t, 3)})
    result["actors"] = actors_out
    result["doors_used"] = list(doors_used.values())
    # locked doors may only be passed after somebody forces or opens them
    for ps in all_passes:
        op = sc.openings[ps["opening"]]
        if op["state"] == "locked" and ps["t"] + 0.05 < unlock_times.get(op["id"], 1e18):
            result["violations"].append({"code": "locked_door_passed", "step": None, "actor": ps["actor"],
                                         "message": f"'{op['label']}' is recorded as locked, but it is passed before anyone forces, opens or unlocks it"})
    if actors_out:
        result["total_duration_s"] = round(max(a["end_s"] for a in actors_out), 3)
        result["total_distance_m"] = round(sum(sg["length_m"] for a in actors_out for sg in a["segments"] if sg["kind"] == "transit"), 3)
    for a in actors_out:
        for st in a["steps"]:
            for note in st["route_notes"]:
                result["route_notes"].append(f"{a['label']}, step {st['k'] + 1} ({st['label']}): {note}")
    return result


# --------------------------------------------------------------------------
# Independent validator: shares no routing code with plan_scenario
# --------------------------------------------------------------------------

class _Regions:
    def __init__(self, layout: dict):
        self.layout = layout
        t2 = layout["wall_thickness_m"] / 2
        R = layout["actor_radius_m"]
        self.t2, self.R = t2, R
        self.levels = {f["level"]: f["floor_y"] for f in layout["levels"]}
        self.walk: Dict[int, List[Tuple[str, Rect]]] = {}
        self.outer: Dict[int, List[Rect]] = {}
        self.boxes: Dict[str, List[Rect]] = {}
        for r in layout["rooms"]:
            self.walk.setdefault(r["level"], []).append((r["id"], _shrink(_room_rect(r), t2 + R)))
            self.outer.setdefault(r["level"], []).append(_expand(_room_rect(r), t2))
        for f in layout["fixtures"]:
            self.boxes.setdefault(f["room"], []).append(_expand(_fixture_rect(f), R))
        self.out_boxes = [_expand(_fixture_rect(o), R) for o in layout.get("outdoor_objects", [])]
        self.corr: Dict[int, List[Rect]] = {}
        for op in layout["openings"]:
            if op["kind"] == "stairs":
                continue
            u = op["width_m"] / 2 - R
            if u <= 0:
                continue
            c, line = op["gap_center_m"], op["line"]
            if op["orient"] == "z":
                rect = (line - t2 - R, line + t2 + R, c - u, c + u)
                if op["kind"] == "external":
                    rect = (line - t2 - R, line + t2, c - u, c + u) if op["wall"] == "east" else (line - t2, line + t2 + R, c - u, c + u)
            else:
                rect = (c - u, c + u, line - t2 - R, line + t2 + R)
                if op["kind"] == "external":
                    rect = (c - u, c + u, line - t2 - R, line + t2) if op["wall"] == "north" else (c - u, c + u, line - t2, line + t2 + R)
            self.corr.setdefault(op["level"], []).append(rect)

    def level(self, y: float) -> int:
        return min(self.levels.items(), key=lambda kv: abs(kv[1] - y))[0]

    def allowed(self, p, level: int) -> bool:
        outers = self.outer.get(level, [])
        if level == 0:
            if not any(_strictly_in_rect(p, o, 1e-7) for o in outers):
                return not any(_strictly_in_rect(p, b, BOX_TOLERANCE_M) for b in self.out_boxes)
        for rid, w in self.walk.get(level, []):
            if _in_rect(p, w, 1e-7):
                return not any(_strictly_in_rect(p, b, BOX_TOLERANCE_M) for b in self.boxes.get(rid, []))
        return any(_in_rect(p, c, 1e-7) for c in self.corr.get(level, []))

    def breakpoints(self, level: int) -> List[Rect]:
        rs: List[Rect] = list(self.outer.get(level, [])) + [w for _, w in self.walk.get(level, [])] + list(self.corr.get(level, []))
        for rid, w in self.walk.get(level, []):
            rs += self.boxes.get(rid, [])
        if level == 0:
            rs += self.out_boxes
        return rs


def leg_violations(a, b, regions: _Regions, level: int) -> List[str]:
    dx, dz = b[0] - a[0], b[2] - a[2]
    ts = {0.0, 1.0}
    for r in regions.breakpoints(level):
        for lo_hi, d, q in ((r[0], dx, a[0]), (r[1], dx, a[0]), (r[2], dz, a[2]), (r[3], dz, a[2])):
            if abs(d) > 1e-12:
                t = (lo_hi - q) / d
                if 0.0 < t < 1.0:
                    ts.add(t)
    seq = sorted(ts)
    for t0, t1 in zip(seq, seq[1:]):
        if t1 - t0 < 1e-9:
            continue
        tm = (t0 + t1) / 2
        pm = [a[0] + dx * tm, 0.0, a[2] + dz * tm]
        if not regions.allowed(pm, level):
            return [f"leg passes through a wall or furniture near x={pm[0]:.2f}, z={pm[2]:.2f}"]
    return []


def validate_plan(plan: Dict[str, Any], layout: dict) -> Dict[str, Any]:
    violations = list(plan.get("violations", []))
    warnings = list(plan.get("warnings", []))
    reg = _Regions(layout)
    sc = get_scene(layout)
    ops = {o["id"]: o for o in layout["openings"]}
    max_speed = 0.0
    for actor in plan.get("actors", []):
        last_end = None
        for sg in actor["segments"]:
            if sg["kind"] == "transit":
                pts = sg["route"]
                if last_end is not None and (_dist(last_end, pts[0]) > 1e-3 or abs(last_end[1] - pts[0][1]) > 1e-3):
                    violations.append({"code": "discontinuous", "step": sg["step"], "actor": actor["id"], "message": "route does not start where the previous step ended"})
                kinds = sg.get("leg_kinds") or ["walk"] * (len(pts) - 1)
                for i, (a, b) in enumerate(zip(pts, pts[1:])):
                    if kinds[i] == "stairs":
                        op = ops.get((sg.get("leg_openings") or [None] * len(kinds))[i] or "")
                        if op is None or op["kind"] != "stairs":
                            violations.append({"code": "path_blocked", "step": sg["step"], "actor": actor["id"], "message": f"step {sg['step'] + 1}: a floor change is not on a stairway"})
                        else:
                            for p in (a, b):
                                if not reg.allowed(p, reg.level(p[1])):
                                    violations.append({"code": "path_blocked", "step": sg["step"], "actor": actor["id"], "message": f"step {sg['step'] + 1}: the stairs start or end inside furniture"})
                        continue
                    if abs(a[1] - b[1]) > 0.2:
                        violations.append({"code": "path_blocked", "step": sg["step"], "actor": actor["id"], "message": f"step {sg['step'] + 1}: a floor change is not on a stairway"})
                        continue
                    for msg in leg_violations(a, b, reg, reg.level((a[1] + b[1]) / 2)):
                        violations.append({"code": "path_blocked", "step": sg["step"], "actor": actor["id"], "message": f"step {sg['step'] + 1}: {msg}"})
                if sg["t1"] > sg["t0"]:
                    max_speed = max(max_speed, sg.get("v_max", 0.0))
                last_end = pts[-1]
            else:
                p = sg["pos"]
                if last_end is not None and (_dist(last_end, p) > 1e-3 or abs(last_end[1] - p[1]) > 1e-3):
                    violations.append({"code": "discontinuous", "step": sg["step"], "actor": actor["id"], "message": "stop is not where the walk ended"})
                if not reg.allowed(p, reg.level(p[1])) and not _is_gap_point(p, layout):
                    violations.append({"code": "stop_blocked", "step": sg["step"], "actor": actor["id"], "message": f"step {sg['step'] + 1}: stop point is inside a wall or furniture"})
                last_end = p
    if max_speed > MAX_HUMAN_SPEED_MPS + 1e-6:
        violations.append({"code": "impossible_speed", "step": None, "actor": None, "message": f"modelled speed {max_speed:.1f} m/s exceeds a human sprint"})

    # camera / witness claims
    claims = []
    obs_by_id = {o["id"]: o for o in layout.get("observers", [])}
    for c in plan.get("observation_claims", []):
        mid = [c["pos"][0], c["pos"][1], c["pos"][2]]
        for oid in c["observers"]:
            ob = obs_by_id[oid]
            ok, why = sc.visible(ob, mid, c["pos"][1])
            claims.append({**c, "observer": oid, "visible": ok, "reason": why})
            if not ok:
                violations.append({"code": "not_visible", "step": c["step"], "actor": c["actor"],
                                   "message": f"step {c['step'] + 1} is claimed to be seen by '{ob['label']}', but {why}"})

    # people close together at the same time (a caution: they would have to meet)
    actors = plan.get("actors", [])
    if len(actors) > 1:
        thr = CONFIG["people_overlap_m"]
        end = max(a["end_s"] for a in actors)
        seen_pairs: set = set()
        t = 0.0
        while t <= end:
            poss = [(a, _actor_pos_at(a, t)) for a in actors]
            for i in range(len(poss)):
                for j in range(i + 1, len(poss)):
                    (a1, p1), (a2, p2) = poss[i], poss[j]
                    if p1 and p2 and abs(p1[1] - p2[1]) < 0.5 and _dist(p1, p2) < thr and (a1["id"], a2["id"]) not in seen_pairs                             and not (_is_still(a1, t) and _is_still(a2, t)):
                        seen_pairs.add((a1["id"], a2["id"]))
                        warnings.append(f"{a1['label']} and {a2['label']} are in the same spot at {t:.0f} s, so they would have to meet or collide")
            t += 0.5
    seen = set()
    uniq = []
    for v in violations:
        key = (v["code"], v.get("step"), v.get("actor"), v["message"])
        if key not in seen:
            seen.add(key)
            uniq.append(v)
    return {
        "is_physically_possible": bool(plan.get("ok")) and not uniq, "violations": uniq, "warnings": warnings,
        "time_adjustments": plan.get("time_adjustments", []), "total_distance_m": plan.get("total_distance_m", 0.0),
        "total_duration_s": plan.get("total_duration_s", 0.0), "max_modelled_speed_mps": round(max_speed, 3),
        "observation_checks": claims, "checks_run": CHECKS_RUN, "checks_not_run": CHECKS_NOT_RUN, "engine_version": ENGINE_VERSION,
    }


def _is_still(actor: dict, t: float) -> bool:
    for sg in actor["segments"]:
        if sg["t0"] - 1e-9 <= t <= sg["t1"] + 1e-9:
            return sg["kind"] == "dwell"
    return True


def _is_gap_point(p, layout: dict) -> bool:
    return any(abs(o["gap_pos"][0] - p[0]) < 1e-3 and abs(o["gap_pos"][2] - p[2]) < 1e-3 for o in layout["openings"])


def _actor_pos_at(actor: dict, t: float) -> Optional[List[float]]:
    segs = actor["segments"]
    if not segs or t < segs[0]["t0"] - 1e-9 or t > segs[-1]["t1"] + 1e-9:
        return None
    for sg in segs:
        if t <= sg["t1"] + 1e-9:
            if sg["kind"] == "dwell":
                return sg["pos"]
            dur = max(sg["t1"] - sg["t0"], 1e-9)
            frac = clamp((t - sg["t0"]) / dur, 0.0, 1.0)
            pts = sg["route"]
            total = _polyline_len(pts) or 1e-9
            target = total * frac
            run = 0.0
            for a, b in zip(pts, pts[1:]):
                d = _dist(a, b)
                if run + d >= target:
                    f = (target - run) / d if d else 0.0
                    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]
                run += d
            return pts[-1]
    return segs[-1].get("pos") or segs[-1]["route"][-1]


def layout_similarity(a: dict, b: dict) -> Dict[str, Any]:
    """How alike two layouts built from the same evidence are (rooms, sizes, furniture,
    doors and their recorded condition). Used to measure run-to-run variation of the model."""
    def jac(x: set, y: set) -> float:
        return 1.0 if not x and not y else len(x & y) / len(x | y)

    ra, rb = {r["id"]: r for r in a["rooms"]}, {r["id"]: r for r in b["rooms"]}
    common = set(ra) & set(rb)
    size = [1.0 - min(1.0, abs(ra[i]["width_m"] * ra[i]["length_m"] - rb[i]["width_m"] * rb[i]["length_m"]) / max(ra[i]["width_m"] * ra[i]["length_m"], 1e-6)) for i in common]
    oa, ob = {o["id"]: o for o in a["openings"]}, {o["id"]: o for o in b["openings"]}
    oc = set(oa) & set(ob)
    parts = {
        "rooms": jac(set(ra), set(rb)), "room_sizes": sum(size) / len(size) if size else 0.0,
        "furniture": jac({f["id"] for f in a["fixtures"]}, {f["id"] for f in b["fixtures"]}),
        "doors": jac(set(oa), set(ob)), "door_conditions": sum(1 for i in oc if oa[i]["state"] == ob[i]["state"]) / len(oc) if oc else 0.0,
    }
    score = sum(parts.values()) / len(parts)
    return {"score": round(score, 3), "parts": {k: round(v, 3) for k, v in parts.items()}, "within_tolerance": score >= 0.8}
