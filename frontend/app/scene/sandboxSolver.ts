// Pure playback maths. No React, no three.js: every person's position, heading,
// pose and the clock at any time t are read straight from the backend's timed
// segments, so what is on screen is exactly what the validator checked.
import type { PlanActor, Scenario, Segment, Vec3 } from "./sandboxTypes";

export interface ActorState {
  id: string;
  label: string;
  role: string;
  color: string;
  pos: Vec3;
  heading: number;
  kind: "transit" | "dwell";
  action: string;
  pose: string;
  placeLabel: string;
  phase: string;
  narrative: string;
  step: number;
  segIndex: number;
  carrying: boolean;
  item: string;
  travelled: number;
  speed: number;
  started: boolean;
  ended: boolean; // past their last step: the evidence says nothing about where they are now
  routingNotes: string[];
  autoRouted: boolean;
  evidenceRefs: string[];
  facePos: Vec3 | null;
  space: string;
}

export interface SimState {
  t: number;
  total: number;
  actors: ActorState[];
  touchedNodeIds: string[];
  effectStates: Record<string, string>;
  primary: ActorState | null;
}

export const SPIRAL_R = 0.7;
const TOUCH_ACTIONS = new Set(["search", "take_item", "struggle", "damage", "open", "close", "drop_item", "unlock", "restrain", "hand_over", "receive"]);

/** Metres (speed-weighted) covered t seconds after a walk starts: accelerate, cruise, brake. */
export function distanceAtTime(L: number, v: number, a: number, tau: number): number {
  if (L <= 0) return 0;
  const dAcc = (v * v) / (2 * a);
  const T = L >= 2 * dAcc ? L / v + v / a : 2 * Math.sqrt(L / a);
  const t = Math.max(0, Math.min(T, tau));
  if (L >= 2 * dAcc) {
    if (t <= v / a) return 0.5 * a * t * t;
    if (t <= T - v / a) return dAcc + v * (t - v / a);
    const r = T - t;
    return L - 0.5 * a * r * r;
  }
  if (t <= T / 2) return 0.5 * a * t * t;
  const r = T - t;
  return L - 0.5 * a * r * r;
}

export function speedAtTime(L: number, v: number, a: number, tau: number): number {
  if (L <= 0) return 0;
  const dAcc = (v * v) / (2 * a);
  const T = L >= 2 * dAcc ? L / v + v / a : 2 * Math.sqrt(L / a);
  const t = Math.max(0, Math.min(T, tau));
  if (L >= 2 * dAcc) {
    if (t <= v / a) return a * t;
    if (t <= T - v / a) return v;
    return a * (T - t);
  }
  return t <= T / 2 ? a * t : a * (T - t);
}

function hHeading(a: Vec3, b: Vec3): number | null {
  const dx = b[0] - a[0];
  const dz = b[2] - a[2];
  return Math.hypot(dx, dz) < 1e-6 ? null : Math.atan2(dx, dz);
}

function legData(seg: Segment) {
  const route = seg.route ?? [];
  const n = Math.max(0, route.length - 1);
  const lengths: number[] = [];
  const factors: number[] = [];
  for (let i = 0; i < n; i++) {
    lengths.push(seg.leg_lengths?.[i] ?? Math.hypot(route[i + 1][0] - route[i][0], route[i + 1][2] - route[i][2]));
    factors.push(seg.leg_factors?.[i] ?? 1);
  }
  return { route, lengths, factors };
}

function pointAtEff(seg: Segment, eff: number): { pos: Vec3; heading: number | null } {
  const { route, lengths, factors } = legData(seg);
  if (route.length === 0) return { pos: [0, 0, 0], heading: null };
  let acc = 0;
  for (let i = 0; i < lengths.length; i++) {
    const effLen = lengths[i] * factors[i];
    if (eff <= acc + effLen || i === lengths.length - 1) {
      const f = effLen > 0 ? Math.min(1, Math.max(0, (eff - acc) / effLen)) : 1;
      const a = route[i];
      const b = route[i + 1];
      if (seg.leg_kinds?.[i] === "stairs") {
        // a compact spiral drawn around (a.x - R, a.z); the angle follows height, so going up and down use the same stairs
        const yLow = Math.min(a[1], b[1]);
        const rise = Math.max(1e-6, Math.abs(b[1] - a[1]));
        const y = a[1] + (b[1] - a[1]) * f;
        const psi = 2 * Math.PI * ((y - yLow) / rise);
        const sign = b[1] >= a[1] ? 1 : -1;
        return {
          pos: [a[0] - SPIRAL_R + SPIRAL_R * Math.cos(psi), y, a[2] + SPIRAL_R * Math.sin(psi)],
          heading: Math.atan2(sign * -Math.sin(psi), sign * Math.cos(psi)),
        };
      }
      let heading = hHeading(a, b);
      if (heading === null) {
        for (let j = i + 1; j < route.length - 1 && heading === null; j++) heading = hHeading(route[j], route[j + 1]);
        for (let j = i - 1; j >= 0 && heading === null; j--) heading = hHeading(route[j], route[j + 1]);
      }
      return { pos: [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f], heading };
    }
    acc += effLen;
  }
  return { pos: route[route.length - 1], heading: null };
}

function boundaryHeading(segs: Segment[], idx: number, dir: 1 | -1): number | null {
  for (let i = idx + dir; i >= 0 && i < segs.length; i += dir) {
    const s = segs[i];
    if (s.kind === "transit" && s.route && s.route.length >= 2) {
      if (dir < 0) {
        for (let j = s.route.length - 1; j > 0; j--) {
          const h = hHeading(s.route[j - 1], s.route[j]);
          if (h !== null) return h;
        }
      } else {
        for (let j = 0; j < s.route.length - 1; j++) {
          const h = hHeading(s.route[j], s.route[j + 1]);
          if (h !== null) return h;
        }
      }
    }
  }
  return null;
}

export function poseFor(action: string, kind: "transit" | "dwell", speed: number): string {
  if (kind === "transit") return speed > 2.4 ? "run" : "walk";
  switch (action) {
    case "lie_down": return "lie";
    case "sit": return "sit";
    case "hide": return "crouch";
    case "take_item": case "open": case "close": case "drop_item": case "hand_over": case "receive": case "unlock": return "reach";
    case "struggle": case "damage": case "restrain": return "struggle";
    case "search": case "look": return "look";
    case "shout": case "call": return "call";
    default: return "stand";
  }
}

function solveActor(actor: PlanActor, t: number): ActorState & { touched: string[] } {
  const segs = actor.segments;
  const base = { id: actor.id, label: actor.label, role: actor.role, color: actor.color };
  if (segs.length === 0) {
    return { ...base, pos: [0, 0, 0], heading: 0, kind: "dwell", action: "wait", pose: "stand", placeLabel: "", phase: "", narrative: "", step: 0, segIndex: 0, carrying: false, item: "",
      travelled: 0, speed: 0, started: false, ended: false, routingNotes: [], autoRouted: false, evidenceRefs: [], facePos: null, space: "", touched: [] };
  }
  const started = t >= segs[0].t0 - 1e-9;
  const ended = t > segs[segs.length - 1].t1 + 1e-9;
  const tc = Math.max(segs[0].t0, Math.min(segs[segs.length - 1].t1, t));
  let idx = segs.findIndex((s) => tc < s.t1);
  if (idx < 0) idx = segs.length - 1;
  const seg = segs[idx];
  let travelled = 0;
  for (let i = 0; i < idx; i++) travelled += segs[i].length_m ?? 0;
  const touched: string[] = [];
  for (let i = 0; i <= idx; i++) {
    const s = segs[i];
    if (s.kind === "dwell" && TOUCH_ACTIONS.has(s.action) && !touched.includes(s.node_id)) touched.push(s.node_id);
  }
  let pos: Vec3;
  let heading: number | null = null;
  let speed = 0;
  if (seg.kind === "transit" && seg.route && seg.route.length >= 2) {
    const tau = Math.max(0, tc - seg.t0);
    const eff = seg.eff_length_m ?? seg.length_m ?? 0;
    const v = seg.v_max ?? 1.4;
    const a = seg.accel ?? 1.2;
    const d = distanceAtTime(eff, v, a, tau);
    const p = pointAtEff(seg, d);
    pos = p.pos;
    heading = p.heading;
    const frac = eff > 0 ? d / eff : 1;
    travelled += (seg.length_m ?? 0) * frac;
    speed = speedAtTime(eff, v, a, tau);
  } else {
    pos = seg.pos ?? [0, 0, 0];
    if (seg.face_pos) heading = hHeading(pos, seg.face_pos);
    if (heading === null) heading = boundaryHeading(segs, idx, -1);
    if (heading === null) heading = boundaryHeading(segs, idx, 1);
  }
  return {
    ...base, pos, heading: heading ?? 0, kind: seg.kind, action: seg.action, pose: poseFor(seg.action, seg.kind, speed), placeLabel: seg.label, phase: seg.phase,
    narrative: seg.narrative, step: seg.step, segIndex: idx, carrying: seg.carrying, item: seg.item, travelled, speed, started, ended,
    routingNotes: seg.routing_notes, autoRouted: seg.auto_routed, evidenceRefs: seg.evidence_refs, facePos: seg.face_pos, space: seg.space, touched,
  };
}

export function totalDuration(scn: Scenario | undefined): number {
  return scn ? Math.max(1, scn.plan.total_duration_s) : 1;
}

export function solve(scn: Scenario | undefined, tRaw: number, focusActor?: string | null): SimState {
  const empty: SimState = { t: 0, total: 1, actors: [], touchedNodeIds: [], effectStates: {}, primary: null };
  if (!scn || scn.plan.actors.length === 0) return empty;
  const total = totalDuration(scn);
  const t = Math.max(0, Math.min(total, tRaw));
  const solved = scn.plan.actors.map((a) => solveActor(a, t));
  const touched: string[] = [];
  for (const s of solved) for (const n of s.touched) if (!touched.includes(n)) touched.push(n);
  const effectStates: Record<string, string> = {};
  for (const e of [...scn.plan.effects].sort((a, b) => a.t - b.t)) if (e.t <= t) effectStates[e.target] = e.state;
  const actors: ActorState[] = solved.map(({ touched: _t, ...rest }) => { void _t; return rest; });
  const primary = actors.find((a) => a.id === focusActor) ?? actors[0] ?? null;
  return { t, total, actors, touchedNodeIds: touched, effectStates, primary };
}

/** Real clock time at model time t, or null when nothing ties the scenario to a clock. */
export function clockAt(scn: Scenario | undefined, t: number): { text: string; estimated: boolean; basis: string } | null {
  const anchors = scn?.time.clock_anchors ?? [];
  if (!scn || anchors.length === 0) return null;
  let a = anchors[0];
  for (const x of anchors) if (x.t_model <= t) a = x;
  const clock = a.sod + (t - a.t_model);
  const norm = ((Math.floor(clock) % 86400) + 86400) % 86400;
  const hh = String(Math.floor(norm / 3600)).padStart(2, "0");
  const mm = String(Math.floor((norm % 3600) / 60)).padStart(2, "0");
  const ss = String(norm % 60).padStart(2, "0");
  return { text: `${hh}:${mm}:${ss}`, estimated: !anchors.some((x) => Math.abs(x.t_model - t) < 1), basis: scn.time.basis };
}

/** 0 at night .. 1 in daylight, from the shown clock (neutral when there is no clock). */
export function daylightAt(clockText: string | undefined): number {
  if (!clockText) return 1;
  const h = parseInt(clockText.slice(0, 2), 10) + parseInt(clockText.slice(3, 5), 10) / 60;
  if (h >= 7 && h <= 18) return 1;
  if (h < 5 || h > 20) return 0;
  return h < 7 ? (h - 5) / 2 : (20 - h) / 2;
}

export function formatDuration(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

export const ACTION_LABEL: Record<string, string> = {
  take_item: "takes an item", drop_item: "puts an item down", hand_over: "hands something over", receive: "receives something", lie_down: "lies down",
  struggle: "struggles", restrain: "restrains someone", damage: "damages something", open: "opens", close: "closes", unlock: "unlocks", wait: "waits", hide: "hides",
  look: "looks around", flee: "runs away", search: "searches", enter: "enters", approach: "approaches", move: "moves", sit: "sits", stand: "stands", shout: "shouts", call: "makes a call", other: "acts",
};


// ---------------------------------------------------------------- skipping stretches where nothing happens

export interface QuietGap { from: number; to: number }
export interface AxisPiece { t0: number; t1: number; d0: number; d1: number; gap: boolean }
export interface TimeAxis { pieces: AxisPiece[]; display: number; gaps: QuietGap[]; skipped: number }

/** Stretches longer than minLen seconds in which nobody is doing anything (everyone has finished or not yet started). */
export function quietGaps(scn: Scenario | undefined, minLen = 40): QuietGap[] {
  if (!scn) return [];
  const total = totalDuration(scn);
  const spans: [number, number][] = [];
  for (const a of scn.plan.actors) for (const g of a.segments) spans.push([g.t0, g.t1]);
  spans.sort((x, y) => x[0] - y[0]);
  const gaps: QuietGap[] = [];
  let reach = 0;
  for (const [a, b] of spans) {
    if (a - reach >= minLen) gaps.push({ from: reach, to: a });
    reach = Math.max(reach, b);
  }
  if (total - reach >= minLen) gaps.push({ from: reach, to: total });
  return gaps;
}

/** A playback clock with each quiet gap shortened to `keep` seconds: the first and last half of that are shown, the middle is skipped. */
export function buildAxis(total: number, gaps: QuietGap[], keep = 30): TimeAxis {
  const pieces: AxisPiece[] = [];
  let t = 0, d = 0, skipped = 0;
  for (const g of gaps) {
    if (g.to - g.from <= keep) continue;
    if (g.from > t) { pieces.push({ t0: t, t1: g.from, d0: d, d1: d + (g.from - t), gap: false }); d += g.from - t; }
    pieces.push({ t0: g.from, t1: g.to, d0: d, d1: d + keep, gap: true });
    d += keep;
    skipped += g.to - g.from - keep;
    t = g.to;
  }
  if (total > t) { pieces.push({ t0: t, t1: total, d0: d, d1: d + (total - t), gap: false }); d += total - t; }
  if (pieces.length === 0) pieces.push({ t0: 0, t1: total, d0: 0, d1: total, gap: false });
  return { pieces, display: d, gaps, skipped };
}

export function toDisplay(ax: TimeAxis, t: number): number {
  for (const p of ax.pieces) {
    if (t > p.t1 && p !== ax.pieces[ax.pieces.length - 1]) continue;
    if (!p.gap) return p.d0 + Math.max(0, Math.min(p.t1 - p.t0, t - p.t0));
    const half = (p.d1 - p.d0) / 2;
    if (t <= p.t0 + half) return p.d0 + Math.max(0, t - p.t0);
    if (t >= p.t1 - half) return p.d0 + half + (t - (p.t1 - half));
    return p.d0 + half; // in the skipped middle
  }
  return ax.display;
}

export function fromDisplay(ax: TimeAxis, d: number): number {
  for (const p of ax.pieces) {
    if (d > p.d1 && p !== ax.pieces[ax.pieces.length - 1]) continue;
    if (!p.gap) return p.t0 + Math.max(0, Math.min(p.d1 - p.d0, d - p.d0));
    const half = (p.d1 - p.d0) / 2;
    const x = Math.max(0, Math.min(p.d1 - p.d0, d - p.d0));
    return x <= half ? p.t0 + x : p.t1 - half + (x - half);
  }
  return ax.pieces[ax.pieces.length - 1].t1;
}
