"""Plan-view pictures of a scenario at chosen moments, for the reviewer model (and for people to audit).

Why plan views: the reviewer's job is to check who is where, what state each door is in, who carries what and who can
see whom. A top-down plan shows that without perspective or things hiding behind walls. (How the 3D view draws things is
tested separately in the browser.) Each frame carries a caption and the clock, so nothing has to be guessed from colour alone.

`plan_frames` chooses WHICH moments to draw, in a fixed order of priority and under a cap:
  required  - the start, the end, the arrival at every step (the important ones if there are many), every change to a door
              or object, every claimed sighting (drawn with the line of sight), every cited clock time
  extra     - mid-walk frames on the longest walks (to catch a route that clips something), just before / after the major
              changes, moments when two people are close together, and one overview of every route
`render_frame` draws one of them.
"""
from __future__ import annotations

import io
import math
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from pipeline import sandbox_geometry as geo

MAX_FRAMES = 28
MAX_STEP_FRAMES = 12
FRAME_W = 960
PANEL_H = 620

STATE_COLOR = {"intact": "#22c55e", "open": "#22d3ee", "forced": "#ef4444", "locked": "#f59e0b", "unknown": "#94a3b8", "closed": "#22c55e", "being worked on": "#fb923c"}
_MAJOR_EFFECT = {"forced", "damaged", "opened", "unlocked"}
_MAJOR_ACTIONS = {"take_item", "damage", "hand_over", "receive", "struggle", "restrain", "unlock"}


def _font(size: int):
    try:
        return ImageFont.load_default(size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


# ---------------------------------------------------------------- what is true at time t

def clock_at(scn: Dict[str, Any], t: float) -> Optional[str]:
    anchors = (scn.get("time") or {}).get("clock_anchors") or []
    if not anchors:
        return None
    a = anchors[0]
    for x in anchors:
        if x["t_model"] <= t:
            a = x
    clock = int(a["sod"] + (t - a["t_model"])) % 86400
    return f"{clock // 3600:02d}:{(clock % 3600) // 60:02d}:{clock % 60:02d}"


def door_state_at(op: Dict[str, Any], effects: List[Dict[str, Any]], t: float, actors: Optional[List[Dict[str, Any]]] = None) -> str:
    """The state at time t. While someone is still working on it (forcing, unlocking, opening) and it has not changed yet, it is 'being worked on'."""
    mine = sorted((e for e in effects if e["target"] == op["id"]), key=lambda e: e["t"])
    forced_later = any(e["state"] == "forced" for e in mine)
    state = "intact" if (op["state"] == "forced" and forced_later) else op["state"]
    for e in mine:
        if e["t"] <= t:
            state = {"forced": "forced", "opened": "open", "unlocked": "open", "closed": "intact", "locked": "locked"}.get(e["state"], state)
    if actors and state not in ("forced", "open"):
        for a in actors:
            if any(g["kind"] == "dwell" and g["node_id"] == op["id"] and g["action"] in ("damage", "unlock", "open") and g["t0"] - 1e-9 <= t <= g["t1"] + 1e-9 for g in a["segments"]):
                return "being worked on"
    return state


def actor_state_at(actor: Dict[str, Any], t: float) -> Dict[str, Any]:
    segs = actor["segments"]
    started = bool(segs) and t >= segs[0]["t0"] - 1e-9
    ended = bool(segs) and t > segs[-1]["t1"] + 1e-9
    pos = geo._actor_pos_at(actor, t)
    if pos is None and segs:
        pos = segs[0].get("pos") or segs[0]["route"][0] if t < segs[0]["t0"] else (segs[-1].get("pos") or segs[-1]["route"][-1])
    seg = next((g for g in segs if t <= g["t1"] + 1e-9), segs[-1] if segs else None)
    return {"pos": pos, "started": started, "ended": ended, "action": seg["action"] if seg else "", "kind": seg["kind"] if seg else "dwell",
            "label": seg["label"] if seg else "", "carrying": bool(seg and seg.get("carrying")), "step": seg["step"] if seg else 0,
            "item": next((g["item"] for g in reversed(segs) if g["t1"] <= t + 1e-9 and g["kind"] == "dwell" and g["action"] == "take_item" and g.get("item")), "") if seg and seg.get("carrying") else ""}


# ---------------------------------------------------------------- which moments

def plan_frames(scn: Dict[str, Any], layout: Dict[str, Any]) -> List[Dict[str, Any]]:
    plan = scn["plan"]
    total = float(plan["total_duration_s"])
    frames: List[Dict[str, Any]] = []
    seen_t: List[float] = []

    def add(t: float, kind: str, reason: str, **kw) -> None:
        t = round(max(0.0, min(total, t)), 2)
        # required kinds are never dropped for being close to another frame; extras are skipped if a frame already shows that moment
        if kind in ("walk", "before", "after", "meeting") and any(abs(t - x) < 0.6 for x in seen_t):
            return
        if kind in ("step", "effect", "clock") and any(f["kind"] == kind and abs(f["t"] - t) < 0.05 and f.get("focus") == kw.get("focus") for f in frames):
            return
        seen_t.append(t)
        frames.append({"t": t, "kind": kind, "reason": reason, **kw})

    add(0.0, "start", "start: where everyone is before anything happens")
    # step arrivals, important ones first when there are more than the cap
    steps = [(a, st) for a in plan["actors"] for st in a["steps"]]
    def weight(item):
        a, st = item
        eff = any(e["actor"] == a["id"] and e["step"] == st["k"] for e in plan["effects"])
        return (0 if eff else 1 if st["action"] in _MAJOR_ACTIONS else 2 if st.get("observed_by") else 3, st["arrive_s"])
    chosen = sorted(steps, key=weight)[:MAX_STEP_FRAMES]
    for a, st in sorted(chosen, key=lambda x: x[1]["arrive_s"]):
        add(st["arrive_s"] + min(1.0, max(0.0, st["depart_s"] - st["arrive_s"]) / 2), "step", f"{a['label']} · step {st['k'] + 1}: {st['action'].replace('_', ' ')} at {st['label']}", focus=a["id"])
    # every change to a door or object
    for e in sorted(plan["effects"], key=lambda e: e["t"]):
        add(e["t"] + 0.5, "effect", f"'{e['target']}' becomes {e['state']} (step {e['step'] + 1})", focus=e["actor"])
    # every claimed sighting, drawn from the observer's side with the line of sight
    for c in plan.get("observation_claims", []):
        for oid in c["observers"]:
            add(c["t"] if "t" in c else _step_time(plan, c), "sighting", f"claimed sighting by '{oid}' of step {c['step'] + 1}", focus=c["actor"], observer=oid)
    # every cited clock time
    for a_ in (scn.get("time") or {}).get("anchors", []):
        add(a_["t_model"] + 0.5, "clock", f"cited clock time {a_['clock_text']} ({a_['actor_label']}, step {a_['step'] + 1})", focus=a_["actor"])
    # extras: mid-walk frames on the longest walks
    walks = sorted(((g["t1"] - g["t0"], a, g) for a in plan["actors"] for g in a["segments"] if g["kind"] == "transit" and (g.get("length_m") or 0) > 6), key=lambda x: -x[0])[:4]
    for dur, a, g in walks:
        for f in (0.25, 0.5, 0.75):
            add(g["t0"] + dur * f, "walk", f"{a['label']} on a long walk ({int(f * 100)}%) to {g['label']}", focus=a["id"])
    # just before / after the major changes
    for e in plan["effects"]:
        if e["state"] in _MAJOR_EFFECT:
            add(max(0.0, e["t"] - 3.0), "before", f"just before '{e['target']}' becomes {e['state']}", focus=e["actor"])
            add(e["t"] + 4.0, "after", f"just after '{e['target']}' became {e['state']}", focus=e["actor"])
    # people close together
    near = _meetings(plan)
    for t, names in near[:4]:
        add(t, "meeting", f"{' and '.join(names)} within 3 m of each other")
    add(total, "end", "end: where everyone is after the last step (people past their last step are shown as 'last known')")
    # one overview of all routes (a still of the whole scenario), always kept
    frames.append({"t": total, "kind": "overview", "reason": "overview: every route drawn, with the order and time of each step"})
    # cap: keep the required kinds first, then extras by priority
    order = {"start": 0, "end": 0, "overview": 0, "step": 1, "effect": 1, "sighting": 1, "clock": 1, "before": 2, "after": 2, "meeting": 2, "walk": 3}
    keep = sorted(range(len(frames)), key=lambda i: (order[frames[i]["kind"]], i))[:MAX_FRAMES]
    out = [frames[i] for i in sorted(keep, key=lambda i: (frames[i]["t"], order[frames[i]["kind"]]))]
    for n, f in enumerate(out, 1):
        f["id"] = f"F{n}"
    return out


def _step_time(plan: Dict[str, Any], claim: Dict[str, Any]) -> float:
    for a in plan["actors"]:
        if a["id"] == claim["actor"]:
            for st in a["steps"]:
                if st["k"] == claim["step"]:
                    return (st["arrive_s"] + st["depart_s"]) / 2
    return 0.0


def _meetings(plan: Dict[str, Any]) -> List[Tuple[float, List[str]]]:
    out: List[Tuple[float, List[str]]] = []
    actors = plan["actors"]
    total = plan["total_duration_s"]
    t = 0.0
    seen = set()
    while t <= total:
        for i, a in enumerate(actors):
            for b in actors[i + 1:]:
                sa, sb = actor_state_at(a, t), actor_state_at(b, t)
                if sa["started"] and sb["started"] and not sa["ended"] and not sb["ended"] and sa["pos"] and sb["pos"]:
                    if abs(sa["pos"][1] - sb["pos"][1]) < 0.5 and math.hypot(sa["pos"][0] - sb["pos"][0], sa["pos"][2] - sb["pos"][2]) < 3.0 and (a["id"], b["id"]) not in seen:
                        seen.add((a["id"], b["id"]))
                        out.append((t, [a["label"], b["label"]]))
        t += 2.0
    return out


# ---------------------------------------------------------------- drawing

def _bounds(layout: Dict[str, Any], scn: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """The window the picture shows: the building plus a margin. Anything further out is drawn as a marker at the edge."""
    xs, zs = [], []
    for r in layout["rooms"]:
        xs += [r["rect"][0], r["rect"][1]]
        zs += [r["rect"][2], r["rect"][3]]
    m = 7.0
    return min(xs) - m, max(xs) + m, min(zs) - m, max(zs) + m


def render_frame(layout: Dict[str, Any], scn: Dict[str, Any], frame: Dict[str, Any], width: int = FRAME_W, redact=None) -> bytes:
    """One plan-view PNG. Multi-floor scenes get one panel per floor, side by side."""
    plan = scn["plan"]
    t = frame["t"]
    R = redact or (lambda x: x)
    levels = sorted({r["level"] for r in layout["rooms"]})
    panels = len(levels)
    pw = width // panels
    x0, x1, z0, z1 = _bounds(layout, scn)
    scale = min((pw - 24) / max(x1 - x0, 1.0), (PANEL_H - 70) / max(z1 - z0, 1.0))
    img = Image.new("RGB", (pw * panels, PANEL_H + 70), "#0b1020")
    d = ImageDraw.Draw(img, "RGBA")
    f_small, f_mid, f_big = _font(11), _font(13), _font(16)
    effects = plan["effects"]
    overview = frame["kind"] == "overview"

    def P(level_i: int, x: float, z: float) -> Tuple[float, float]:
        return level_i * pw + 12 + (x - x0) * scale, 40 + (z1 - z) * scale  # north (+z) is up

    states = {a["id"]: actor_state_at(a, t) for a in plan["actors"]}

    def inside(x: float, z: float) -> bool:
        return x0 <= x <= x1 and z0 <= z <= z1

    edge_n = [0]

    def edge_marker(li: int, x: float, z: float, label: str, color: str) -> None:
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        ex, ez = min(max(x, x0 + 1.0), x1 - 1.0), min(max(z, z0 + 1.0), z1 - 1.0)
        dist = math.hypot(x - cx, z - cz)
        compass = ("N" if z - cz > abs(x - cx) else "S" if cz - z > abs(x - cx) else "E" if x > cx else "W")
        mx, my = P(li, ex, ez)
        my += 14 * edge_n[0]
        edge_n[0] += 1
        d.polygon([(mx, my - 8), (mx - 7, my + 6), (mx + 7, my + 6)], fill=color)
        d.text((mx + 10, my - 6), f"{label[:24]} ({dist:.0f} m {compass}, off the picture)", fill=color, font=f_small)
    for li, lv in enumerate(levels):
        d.text((li * pw + 14, 44), f"floor {lv}" if panels > 1 else "", fill="#94a3b8", font=f_mid)
        for r in layout["rooms"]:
            if r["level"] != lv:
                continue
            ax, ay = P(li, r["rect"][0], r["rect"][3])
            bx, by = P(li, r["rect"][1], r["rect"][2])
            d.rectangle([ax, ay, bx, by], fill="#222b4a" if r.get("observed", True) else "#1b2238", outline="#475569", width=3)
            d.text((ax + 6, ay + 4), R(r["label"])[:28], fill="#cbd5e1", font=f_mid)
        for f in layout["fixtures"]:
            room = next((r for r in layout["rooms"] if r["id"] == f["room"]), None)
            if not room or room["level"] != lv:
                continue
            w, dp = f["footprint_m"]
            ax, ay = P(li, f["pos"][0] - w / 2, f["pos"][2] + dp / 2)
            bx, by = P(li, f["pos"][0] + w / 2, f["pos"][2] - dp / 2)
            d.rectangle([ax, ay, bx, by], fill="#6b4a2f", outline="#a16207")
            d.text((ax + 2, ay + 1), R(f["label"])[:16], fill="#e7c89b", font=f_small)
        for o in layout["openings"]:
            if o["kind"] == "stairs":
                ra = next((r for r in layout["rooms"] if r["id"] == o["room_a"]), None)
                rb = next((r for r in layout["rooms"] if r["id"] == o.get("room_b")), None)
                if ra and rb and lv in (ra["level"], rb["level"]):
                    cx, cy = P(li, o["gap_pos"][0] - 0.7, o["gap_pos"][2])
                    d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline="#fde68a", width=2)
                    d.text((cx - 10, cy - 6), "stairs", fill="#fde68a", font=f_small)
                continue
            lvl = o.get("level", 0)
            if lvl != lv:
                continue
            st = door_state_at(o, effects, t, plan["actors"])
            gx, gy = P(li, o["gap_pos"][0], o["gap_pos"][2])
            half = max(o["width_m"] * scale / 2, 6)
            col = STATE_COLOR.get(st, "#94a3b8")
            if o["orient"] == "x":
                d.line([gx - half, gy, gx + half, gy], fill=col, width=6)
            else:
                d.line([gx, gy - half, gx, gy + half], fill=col, width=6)
            d.text((gx + 4, gy + 4), f"{R(o['label'])[:18]}: {st}", fill=col, font=f_small)
        if lv == 0:
            for ob in layout.get("outdoor_objects", []):
                if not inside(ob["pos"][0], ob["pos"][2]):
                    edge_marker(li, ob["pos"][0], ob["pos"][2], R(ob["label"]), "#94a3b8")
                    continue
                ax, ay = P(li, ob["pos"][0] - ob["footprint_m"][0] / 2, ob["pos"][2] + ob["footprint_m"][1] / 2)
                bx, by = P(li, ob["pos"][0] + ob["footprint_m"][0] / 2, ob["pos"][2] - ob["footprint_m"][1] / 2)
                d.rectangle([ax, ay, bx, by], fill="#334155", outline="#64748b")
                d.text((ax, by + 1), R(ob["label"])[:20], fill="#94a3b8", font=f_small)
        for ob in layout.get("observers", []):
            if ob.get("level", 0) != lv:
                continue
            col = "#3b82f6" if ob["kind"] == "camera" else "#a855f7"
            if not inside(ob["pos"][0], ob["pos"][2]):
                edge_marker(li, ob["pos"][0], ob["pos"][2], R(ob["label"]), col)
                continue
            ox, oy = P(li, ob["pos"][0], ob["pos"][2])
            fov = math.radians(min(ob["fov_deg"], 360))
            rng = min(ob["range_m"], 14) * scale
            theta = math.degrees(math.atan2(-math.cos(ob["yaw"]), math.sin(ob["yaw"])))  # PIL measures angles clockwise on screen from the right
            d.pieslice([ox - rng, oy - rng, ox + rng, oy + rng], theta - math.degrees(fov) / 2, theta + math.degrees(fov) / 2,
                       fill=(59, 130, 246, 40) if ob["kind"] == "camera" else (168, 85, 247, 40))
            d.ellipse([ox - 6, oy - 6, ox + 6, oy + 6], fill=col)
            d.text((ox + 8, oy - 6), R(ob["label"])[:24], fill=col, font=f_small)
        # routes
        for a in plan["actors"]:
            col = a["color"]
            for g in a["segments"]:
                if g["kind"] != "transit" or not g.get("route"):
                    continue
                pts = [P(li, p[0], p[2]) for p in g["route"] if inside(p[0], p[2]) and abs(p[1] - layout["levels"][next((i for i, l in enumerate(layout["levels"]) if l["level"] == lv), 0)]["floor_y"]) < 0.6]
                if len(pts) >= 2 and (overview or (g["t1"] <= t and t - g["t1"] <= 25) or g["t0"] <= t <= g["t1"]):
                    d.line(pts, fill=col, width=3 if overview else 2)
                    if overview:
                        mx, my = pts[len(pts) // 2]
                        d.text((mx + 3, my - 12), f"{R(a['label']).split()[0][:8]} s{g['step'] + 1} {g['t0']:.0f}s", fill=col, font=f_small)
        # people
        if not overview:
            for a in plan["actors"]:
                s = states[a["id"]]
                if not s["pos"]:
                    continue
                if abs(s["pos"][1] - layout["levels"][next((i for i, l in enumerate(layout["levels"]) if l["level"] == lv), 0)]["floor_y"]) > 1.8:
                    continue
                if not inside(s["pos"][0], s["pos"][2]):
                    edge_marker(li, s["pos"][0], s["pos"][2], f"{R(a['label'])} ({a['role']})" + (" last known" if s["ended"] else ""), a["color"])
                    continue
                px, py = P(li, s["pos"][0], s["pos"][2])
                rad = max(7, 0.45 * scale)
                ghost = not s["started"] or s["ended"]
                if ghost:
                    d.ellipse([px - rad, py - rad, px + rad, py + rad], outline=a["color"], width=2)
                else:
                    d.ellipse([px - rad, py - rad, px + rad, py + rad], fill=a["color"], outline="#ffffff", width=2)
                tag = f"{R(a['label'])[:22]} ({a['role']})" + (" last known" if s["ended"] else " not yet shown" if not s["started"] else f": {s['action'].replace('_', ' ')}")
                d.text((px + rad + 3, py - 7), tag, fill="#ffffff" if not ghost else "#94a3b8", font=f_small)
                if s["carrying"] and not ghost:
                    d.rectangle([px - 4, py + rad + 2, px + 4, py + rad + 9], fill="#fbbf24")
                    d.text((px + 7, py + rad + 1), (s["item"] or "carrying")[:22], fill="#fbbf24", font=f_small)
    # sighting: line from the observer to the person, with the engine's own verdict
    caption_extra = ""
    if frame["kind"] == "sighting":
        ob = next((o for o in layout.get("observers", []) if o["id"] == frame.get("observer")), None)
        s = states.get(frame.get("focus"))
        if ob and s and s["pos"]:
            sc = geo.get_scene(layout)
            ok, why = sc.visible(ob, s["pos"], s["pos"][1])
            li = levels.index(ob.get("level", 0)) if ob.get("level", 0) in levels else 0
            a_, b_ = P(li, ob["pos"][0], ob["pos"][2]), P(li, s["pos"][0], s["pos"][2])
            d.line([a_, b_], fill="#22c55e" if ok else "#ef4444", width=3)
            caption_extra = f" | line of sight: {'clear' if ok else 'BLOCKED'} ({why})"[:150]
    # header and legend
    clk = clock_at(scn, t)
    d.rectangle([0, 0, pw * panels, 38], fill="#111827")
    d.text((10, 4), f"{frame['id']}  t={t:.0f}s" + (f"  clock {clk}" if clk else "  (no real clock)") + f"   {R(scn['title'])[:60]}", fill="#e5e7eb", font=f_big)
    d.text((10, 22), (R(frame["reason"]) + caption_extra)[:150], fill="#fbbf24", font=f_mid)
    legend = "door colours: green=closed/intact, orange=locked, light orange=being forced or opened right now, red=forced, cyan=open   |   filled circle = person acting, hollow = not yet shown or last known   |   yellow box = carried item"
    d.text((10, PANEL_H + 48), legend, fill="#64748b", font=f_small)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def frame_caption(scn: Dict[str, Any], frame: Dict[str, Any], redact=None) -> str:
    """The same information as text, so the reviewer never has to read it from colour alone."""
    plan = scn["plan"]
    t = frame["t"]
    R = redact or (lambda x: x)
    rows = []
    for a in plan["actors"]:
        s = actor_state_at(a, t)
        where = "not yet shown" if not s["started"] else ("last known position after their last step" if s["ended"] else f"{s['action'].replace('_', ' ')} at {s['label']}")
        rows.append(f"{R(a['label'])} ({a['role']}): {R(where)}{' carrying ' + (s['item'] or 'something') if s['carrying'] and s['started'] and not s['ended'] else ''}")
    return f"{frame['id']} [{frame['kind']}] t={t:.0f}s{(' clock ' + clock_at(scn, t)) if clock_at(scn, t) else ''}: {R(frame['reason'])}. " + "; ".join(rows)
