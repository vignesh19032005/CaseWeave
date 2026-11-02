"use client";

import React, { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import type { InspectedItem, Layout, Observer, Opening, OpeningState, Room, Scenario, Vec3 } from "./sandboxTypes";
import { SPIRAL_R } from "./sandboxSolver";
import type { ActorState, SimState } from "./sandboxSolver";
import { FurnitureModel, inferKind } from "./SandboxFurniture";

export type CameraMode = "overview" | "topdown" | "follow" | `observer:${string}`;

const STATE_COLOR: Record<OpeningState, string> = { forced: "#ef4444", intact: "#22c55e", locked: "#a855f7", open: "#38bdf8", unknown: "#94a3b8" };
const STATE_TEXT: Record<OpeningState, string> = {
  forced: "recorded as forced in evidence", intact: "recorded as intact in evidence", locked: "recorded as locked in evidence",
  open: "recorded as open", unknown: "condition not established by evidence",
};
const OVERLAY_COLORS = ["#38bdf8", "#f472b6", "#a3e635", "#fbbf24", "#c084fc", "#2dd4bf"];
const LABEL_SCREEN_HEIGHT = 0.02;
const LABEL_MAX_CHARS = 34;

// ---------------------------------------------------------------- labels (no DOM roots, no font download)

function Label3D({ text: full, color, bg, position }: { text: string; color: string; bg: string; position: Vec3 }) {
  const text = full.length > LABEL_MAX_CHARS ? full.slice(0, LABEL_MAX_CHARS - 1).trimEnd() + "…" : full;
  const made = useMemo(() => {
    const c = document.createElement("canvas");
    const ctx = c.getContext("2d");
    const font = "600 30px system-ui, sans-serif";
    if (!ctx) return null;
    ctx.font = font;
    const w = Math.ceil(ctx.measureText(text).width) + 28;
    c.width = w;
    c.height = 52;
    ctx.font = font;
    ctx.fillStyle = bg;
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.roundRect(2, 2, w - 4, 48, 10);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = color;
    ctx.textBaseline = "middle";
    ctx.fillText(text, 14, 27);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    return { tex, aspect: w / 52 };
  }, [text, color, bg]);
  useEffect(() => () => made?.tex.dispose(), [made]);
  if (!made) return null;
  return (
    <sprite position={position} scale={[LABEL_SCREEN_HEIGHT * made.aspect, LABEL_SCREEN_HEIGHT, 1]} renderOrder={20} raycast={() => null}>
      <spriteMaterial map={made.tex} transparent depthTest={false} sizeAttenuation={false} />
    </sprite>
  );
}

// ---------------------------------------------------------------- floor texture

let floorBase: THREE.CanvasTexture | null = null;
function floorTexture(w: number, l: number): THREE.Texture {
  if (!floorBase) {
    const c = document.createElement("canvas");
    c.width = c.height = 128;
    const ctx = c.getContext("2d");
    if (ctx) {
      ctx.fillStyle = "#cfd6df";
      ctx.fillRect(0, 0, 128, 128);
      ctx.strokeStyle = "#aab4c2";
      ctx.lineWidth = 2;
      ctx.strokeRect(1, 1, 126, 126);
      ctx.strokeStyle = "#bcc5d1";
      ctx.beginPath();
      ctx.moveTo(64, 0); ctx.lineTo(64, 128); ctx.moveTo(0, 64); ctx.lineTo(128, 64);
      ctx.stroke();
    }
    floorBase = new THREE.CanvasTexture(c);
    floorBase.wrapS = floorBase.wrapT = THREE.RepeatWrapping;
    floorBase.colorSpace = THREE.SRGBColorSpace;
  }
  const t = floorBase.clone();
  t.repeat.set(Math.max(1, w / 1.2), Math.max(1, l / 1.2));
  t.needsUpdate = true;
  return t;
}

// ---------------------------------------------------------------- camera

function bounds(layout: Layout) {
  const xs = layout.rooms.flatMap((r) => [r.rect[0], r.rect[1]]);
  const zs = layout.rooms.flatMap((r) => [r.rect[2], r.rect[3]]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), z0 = Math.min(...zs), z1 = Math.max(...zs);
  return { cx: (x0 + x1) / 2, cz: (z0 + z1) / 2, diag: Math.max(8, Math.hypot(x1 - x0, z1 - z0)) };
}

function CameraRig({ layout, mode, sim, focus, dragMode }: { layout: Layout; mode: CameraMode; sim: SimState; focus: Vec3 | null; dragMode: "rotate" | "move" }) {
  const controls = useRef<React.ComponentRef<typeof OrbitControls>>(null);
  const wantPos = useRef(new THREE.Vector3());
  const wantLook = useRef(new THREE.Vector3());
  const settling = useRef(true);
  const b = useMemo(() => bounds(layout), [layout]);
  const observer: Observer | undefined = mode.startsWith("observer:") ? layout.observers.find((o) => o.id === mode.slice(9)) : undefined;
  const floorY = (room: string) => layout.rooms.find((r) => r.id === room)?.floor_y ?? 0;

  useEffect(() => {
    if (mode === "follow" || observer) return;
    if (mode === "topdown") {
      wantPos.current.set(b.cx + 0.01, b.diag * 1.15, b.cz + 0.01);
      wantLook.current.set(b.cx, 0, b.cz);
    } else {
      wantPos.current.set(b.cx + b.diag * 0.7, b.diag * 0.88, b.cz - b.diag * 0.95);
      wantLook.current.set(b.cx, 0.6, b.cz);
    }
    settling.current = true;
  }, [mode, b, observer]);

  useEffect(() => {
    if (!focus) return;
    wantLook.current.set(focus[0], focus[1] + 0.8, focus[2]);
    const d = Math.max(3.5, b.diag * 0.22);
    wantPos.current.set(focus[0] + d * 0.6, focus[1] + d * 0.85, focus[2] - d * 0.9);
    settling.current = true;
  }, [focus, b]);

  useFrame((st, delta) => {
    const camera = st.camera;
    const cam = camera as THREE.PerspectiveCamera;
    const c = controls.current;
    if (observer) {
      cam.fov = Math.max(30, Math.min(110, observer.fov_deg));
      cam.updateProjectionMatrix();
      const y = floorY(observer.room) + observer.eye_height_m;
      cam.position.set(observer.pos[0], y, observer.pos[2]);
      cam.lookAt(observer.pos[0] + Math.sin(observer.yaw) * 6, y - 0.9, observer.pos[2] + Math.cos(observer.yaw) * 6);
      return;
    }
    if (cam.fov !== 46) {
      cam.fov = 46;
      cam.updateProjectionMatrix();
    }
    if (mode === "follow" && sim.primary) {
      const p = sim.primary;
      wantPos.current.set(p.pos[0] - Math.sin(p.heading) * 3.6, p.pos[1] + 2.3, p.pos[2] - Math.cos(p.heading) * 3.6);
      wantLook.current.set(p.pos[0], p.pos[1] + 1.1, p.pos[2]);
      settling.current = true;
    }
    if (!settling.current) return;
    const k = 1 - Math.exp(-delta * 6); // frame-rate independent, so it settles at the same speed on slow machines
    camera.position.lerp(wantPos.current, k);
    if (c) {
      c.target.lerp(wantLook.current, k);
      c.update();
    }
    if (mode !== "follow" && camera.position.distanceTo(wantPos.current) < 0.05) settling.current = false;
  });

  return (
    <OrbitControls ref={controls} makeDefault enabled={!observer} screenSpacePanning mouseButtons={{ LEFT: dragMode === "move" ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN }} enableDamping dampingFactor={0.08} minDistance={0.8} maxDistance={160} maxPolarAngle={Math.PI / 2.02}
      onStart={() => { if (mode !== "follow") settling.current = false; }} />
  );
}

// ---------------------------------------------------------------- building shell

type Seg = { orient: "x" | "z"; line: number; a: number; b: number; h: number; y: number; level: number };

function wallSegments(layout: Layout, maxLevel: number | null): { segs: Seg[]; lintels: Seg[] } {
  const groups = new Map<string, { orient: "x" | "z"; line: number; level: number; y: number; h: number; ivs: [number, number][]; gaps: [number, number][] }>();
  for (const r of layout.rooms) {
    if (maxLevel !== null && r.level > maxLevel) continue;
    const [x0, x1, z0, z1] = r.rect;
    const edges: ["x" | "z", number, number, number][] = [["x", z0, x0, x1], ["x", z1, x0, x1], ["z", x0, z0, z1], ["z", x1, z0, z1]];
    for (const [orient, line, a, b] of edges) {
      const key = `${orient}|${line.toFixed(3)}|${r.level}`;
      const g = groups.get(key) ?? { orient, line, level: r.level, y: r.floor_y, h: r.height_m, ivs: [], gaps: [] };
      g.ivs.push([a, b]);
      g.h = Math.max(g.h, r.height_m);
      groups.set(key, g);
    }
  }
  for (const op of layout.openings) {
    if (op.kind === "stairs" || !op.orient) continue;
    const g = groups.get(`${op.orient}|${op.line.toFixed(3)}|${op.level}`);
    if (g) g.gaps.push([op.gap_center_m - op.width_m / 2, op.gap_center_m + op.width_m / 2]);
  }
  const segs: Seg[] = [];
  const lintels: Seg[] = [];
  for (const g of groups.values()) {
    const merged: [number, number][] = [];
    for (const iv of [...g.ivs].sort((p, q) => p[0] - q[0])) {
      const last = merged[merged.length - 1];
      if (last && iv[0] <= last[1] + 1e-6) last[1] = Math.max(last[1], iv[1]);
      else merged.push([iv[0], iv[1]]);
    }
    for (const [a, b] of merged) {
      let cur = a;
      for (const [lo, hi] of g.gaps.filter(([l, h2]) => h2 > a && l < b).sort((p, q) => p[0] - q[0])) {
        if (lo > cur + 0.01) segs.push({ orient: g.orient, line: g.line, a: cur, b: lo, h: g.h, y: g.y, level: g.level });
        lintels.push({ orient: g.orient, line: g.line, a: lo, b: hi, h: g.h, y: g.y, level: g.level });
        cur = Math.max(cur, hi);
      }
      if (cur < b - 0.01) segs.push({ orient: g.orient, line: g.line, a: cur, b, h: g.h, y: g.y, level: g.level });
    }
  }
  return { segs, lintels };
}

function Shell({ layout, cutaway, maxLevel, onInspect }: { layout: Layout; cutaway: boolean; maxLevel: number | null; onInspect: (i: InspectedItem) => void }) {
  const T = layout.wall_thickness_m;
  const { segs, lintels } = useMemo(() => wallSegments(layout, maxLevel), [layout, maxLevel]);
  const click = (e: { stopPropagation: () => void }) => {
    e.stopPropagation();
    onInspect({
      title: "Wall", kind: "Wall", nodeKind: "wall", basis: "derived",
      description: `Drawn from the room sizes (${layout.dimensions_basis === "assumed" ? "assumed, not measured" : layout.dimensions_basis}). A wall is only as reliable as those sizes.`,
    });
  };
  return (
    <group>
      {segs.map((s, i) => {
        const h = cutaway ? Math.min(s.h, 1.1) : s.h;
        const len = s.b - s.a + (s.orient === "x" ? T : 0);
        const mid = (s.a + s.b) / 2;
        const size: Vec3 = s.orient === "x" ? [len, h, T] : [T, h, len];
        const pos: Vec3 = s.orient === "x" ? [mid, s.y + h / 2, s.line] : [s.line, s.y + h / 2, mid];
        return (
          <mesh key={i} position={pos} onClick={click} castShadow receiveShadow>
            <boxGeometry args={size} />
            <meshStandardMaterial color="#5b6b82" roughness={0.75} transparent={cutaway} opacity={cutaway ? 0.95 : 1} />
          </mesh>
        );
      })}
      {!cutaway && lintels.map((s, i) => {
        const lh = s.h - layout.door_height_m;
        if (lh <= 0.05) return null;
        const size: Vec3 = s.orient === "x" ? [s.b - s.a, lh, T] : [T, lh, s.b - s.a];
        const mid = (s.a + s.b) / 2;
        const y = s.y + layout.door_height_m + lh / 2;
        return (
          <mesh key={`l${i}`} position={s.orient === "x" ? [mid, y, s.line] : [s.line, y, mid]}>
            <boxGeometry args={size} />
            <meshStandardMaterial color="#5b6b82" />
          </mesh>
        );
      })}
    </group>
  );
}

type Rect4 = [number, number, number, number];

/** The floor slab as boxes around a rectangular opening, so a person can climb through it. */
function slabPieces(r: Rect4, hole: Rect4 | null): Rect4[] {
  if (!hole) return [r];
  const hx0 = Math.max(r[0], hole[0]), hx1 = Math.min(r[1], hole[1]), hz0 = Math.max(r[2], hole[2]), hz1 = Math.min(r[3], hole[3]);
  if (hx0 >= hx1 || hz0 >= hz1) return [r];
  return ([[r[0], hx0, r[2], r[3]], [hx1, r[1], r[2], r[3]], [hx0, hx1, r[2], hz0], [hx0, hx1, hz1, r[3]]] as Rect4[]).filter((q) => q[1] - q[0] > 0.01 && q[3] - q[2] > 0.01);
}

function Floor({ room, hole, onInspect }: { room: Room; hole: Rect4 | null; onInspect: (i: InspectedItem) => void }) {
  const w = room.rect[1] - room.rect[0];
  const l = room.rect[3] - room.rect[2];
  const tex = useMemo(() => floorTexture(w, l), [w, l]);
  useEffect(() => () => tex.dispose(), [tex]);
  const cx = (room.rect[0] + room.rect[1]) / 2;
  const cz = (room.rect[2] + room.rect[3]) / 2;
  return (
    <group
      onClick={(e) => {
        e.stopPropagation();
        onInspect({
          id: room.id, nodeKind: "room", title: room.label, kind: `Room, floor ${room.level} (${w.toFixed(1)} x ${l.toFixed(1)} m)`, basis: room.basis,
          description: `Size is ${room.dimensions_basis}.${room.observed ? "" : " The evidence says nothing about the inside of this room."}${room.placement_note ? " " + room.placement_note + "." : ""}`,
          refs: room.evidence_refs, focus: [cx, room.floor_y, cz],
        });
      }}
    >
      {hole ? slabPieces(room.rect, hole).map((q, i) => (
        <mesh key={i} position={[(q[0] + q[1]) / 2, room.floor_y - 0.06, (q[2] + q[3]) / 2]} receiveShadow>
          <boxGeometry args={[q[1] - q[0], 0.12, q[3] - q[2]]} />
          <meshStandardMaterial color="#4b5778" roughness={0.85} />
        </mesh>
      )) : (
        <mesh position={[cx, room.floor_y - 0.06, cz]} receiveShadow>
          <boxGeometry args={[w, 0.12, l]} />
          <meshStandardMaterial map={tex} roughness={0.85} />
        </mesh>
      )}
      {!room.observed && (
        <mesh position={[cx, room.floor_y + 0.01, cz]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[w - 0.3, l - 0.3]} />
          <meshBasicMaterial color="#64748b" transparent opacity={0.45} />
        </mesh>
      )}
    </group>
  );
}

/** Where stairs arrive from below into this room, the opening in its floor. */
function stairHole(layout: Layout, room: Room): Rect4 | null {
  for (const op of layout.openings) {
    if (op.kind !== "stairs") continue;
    const other = op.room_a === room.id ? layout.rooms.find((r) => r.id === op.room_b) : op.room_b === room.id ? layout.rooms.find((r) => r.id === op.room_a) : undefined;
    if (!other || other.floor_y >= room.floor_y) continue;
    const cx = op.gap_pos[0] - SPIRAL_R, cz = op.gap_pos[2], h = SPIRAL_R + 0.3;
    return [cx - h, cx + h, cz - h, cz + h];
  }
  return null;
}

function Ground({ layout }: { layout: Layout }) {
  const b = bounds(layout);
  const size = b.diag * 2.6 + 30;
  // with a cellar the ground sits at its floor, otherwise the opaque ground would hide it
  const gy = Math.min(0, ...layout.levels.map((l) => l.floor_y));
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[b.cx, gy - 0.13, b.cz]} receiveShadow>
        <planeGeometry args={[size, size]} />
        <meshStandardMaterial color="#26302f" roughness={1} />
      </mesh>
      <gridHelper args={[size, Math.round(size / 2), "#34403f", "#2c3736"]} position={[b.cx, gy - 0.12, b.cz]} />
    </group>
  );
}

// ---------------------------------------------------------------- doors, stairs

function DoorLeaf({ op, layout, actors, state, shut }: { op: Opening; layout: Layout; actors: ActorState[]; state: OpeningState; shut: boolean }) {
  const pivot = useRef<THREE.Group>(null);
  const angle = useRef(0);
  const h = layout.door_height_m;
  const w = op.width_m;
  const y = layout.rooms.find((r) => r.id === op.room_a)?.floor_y ?? 0;
  useFrame(() => {
    let near = 99;
    for (const a of actors) near = Math.min(near, Math.hypot(a.pos[0] - op.gap_pos[0], a.pos[2] - op.gap_pos[2]) + Math.abs(a.pos[1] - y) * 3);
    // a locked or not-yet-forced door stays shut however close someone stands; a forced one is only prised ajar until someone goes through
    const target = shut ? 0 : state === "forced" ? 0.5 : near < 1.5 ? 1.35 : state === "open" ? 0.9 : 0;
    angle.current += (target - angle.current) * 0.12;
    if (pivot.current) pivot.current.rotation.y = -angle.current;
  });
  const color = STATE_COLOR[state];
  return (
    <group position={[op.gap_pos[0], y, op.gap_pos[2]]} rotation={[0, op.orient === "z" ? Math.PI / 2 : 0, 0]}>
      <group ref={pivot} position={[-w / 2, 0, 0]}>
        <mesh position={[w / 2, h / 2, 0]} castShadow>
          <boxGeometry args={[w - 0.04, h - 0.04, 0.05]} />
          <meshStandardMaterial color={state === "forced" ? "#7f1d1d" : "#8b7355"} roughness={0.6} transparent opacity={0.95} />
        </mesh>
        <mesh position={[w - 0.12, h * 0.48, 0.05]}>
          <sphereGeometry args={[0.04, 8, 8]} />
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.4} />
        </mesh>
      </group>
    </group>
  );
}

function Doors({ layout, state, forcedLater, showLabels, selectedId, actors, maxLevel, onInspect }: {
  layout: Layout; state: Record<string, string>; forcedLater: Set<string>; showLabels: boolean; selectedId: string | null; actors: ActorState[]; maxLevel: number | null; onInspect: (i: InspectedItem) => void;
}) {
  const T = layout.wall_thickness_m;
  return (
    <group>
      {layout.openings.filter((o) => o.kind !== "stairs" && (maxLevel === null || o.level <= maxLevel)).map((op) => {
        const cur = (state[op.id] === "forced" ? "forced" : state[op.id] === "unlocked" || state[op.id] === "opened" ? "open" : (op.state === "forced" && forcedLater.has(op.id) ? "intact" : op.state)) as OpeningState; // a door the scenario forces later is shown intact until then
        const color = STATE_COLOR[cur];
        const y = layout.rooms.find((r) => r.id === op.room_a)?.floor_y ?? 0;
        return (
          <group key={op.id}>
            <group
              position={[op.gap_pos[0], y, op.gap_pos[2]]} rotation={[0, op.orient === "z" ? Math.PI / 2 : 0, 0]}
              onClick={(e) => {
                e.stopPropagation();
                onInspect({
                  id: op.id, nodeKind: "opening", title: op.label,
                  kind: `${op.kind === "external" ? "Door to the outside" : "Door between rooms"} (${op.width_m.toFixed(2)} m wide)`, basis: op.basis,
                  description: `Condition: ${STATE_TEXT[op.state]}.${op.state_note ? " " + op.state_note : ""}${op.passable ? "" : " Too narrow for a person to pass."}${op.reachable ? "" : " Blocked by furniture."}`,
                  refs: op.evidence_refs, focus: op.gap_pos,
                });
              }}
            >
              <mesh position={[0, 0.025, 0]}>
                <boxGeometry args={[op.width_m, 0.05, T + 0.12]} />
                <meshStandardMaterial color={color} emissive={color} emissiveIntensity={selectedId === op.id ? 0.9 : 0.35} />
              </mesh>
              {[-1, 1].map((s) => (
                <mesh key={s} position={[(s * op.width_m) / 2, layout.door_height_m / 2, 0]}>
                  <boxGeometry args={[0.07, layout.door_height_m, T + 0.06]} />
                  <meshStandardMaterial color="#cbd5e1" />
                </mesh>
              ))}
            </group>
            <DoorLeaf op={op} layout={layout} actors={actors} state={cur} shut={state[op.id] === undefined && (op.state === "locked" || forcedLater.has(op.id))} />
            {(showLabels || selectedId === op.id || state[op.id] === "forced") && <Label3D text={`${op.label} · ${cur}`} color={color} bg="#0b1020e6" position={[op.gap_pos[0], y + 0.7, op.gap_pos[2]]} />}
          </group>
        );
      })}
    </group>
  );
}

function Stairs({ layout, maxLevel, showLabels, onInspect }: { layout: Layout; maxLevel: number | null; showLabels: boolean; onInspect: (i: InspectedItem) => void }) {
  return (
    <group>
      {layout.openings.filter((o) => o.kind === "stairs").map((op) => {
        const ra = layout.rooms.find((r) => r.id === op.room_a);
        const rb = layout.rooms.find((r) => r.id === op.room_b);
        if (!ra || !rb || (maxLevel !== null && Math.max(ra.level, rb.level) > maxLevel)) return null;
        const y0 = Math.min(ra.floor_y, rb.floor_y);
        const rise = Math.abs(ra.floor_y - rb.floor_y);
        const n = Math.max(8, Math.ceil(rise / 0.18));
        const cx = op.gap_pos[0] - SPIRAL_R;
        const cz = op.gap_pos[2];
        return (
          <group
            key={op.id}
            onClick={(e) => {
              e.stopPropagation();
              onInspect({ id: op.id, nodeKind: "opening", title: op.label, kind: `Stairs between floors ${ra.level} and ${rb.level}`, basis: op.basis,
                description: "Drawn as a compact spiral staircase so it fits any room. Only the climb is modelled, not the exact stair shape.", refs: op.evidence_refs, focus: op.gap_pos });
            }}
          >
            <mesh position={[cx, y0 + rise / 2, cz]}><cylinderGeometry args={[0.08, 0.08, rise, 10]} /><meshStandardMaterial color="#94a3b8" /></mesh>
            {Array.from({ length: n }, (_, i) => {
              const psi = (2 * Math.PI * (i + 1)) / n;
              return (
                <mesh key={i} position={[cx + SPIRAL_R * Math.cos(psi), y0 + (i + 1) * (rise / n), cz + SPIRAL_R * Math.sin(psi)]} rotation={[0, -psi, 0]} castShadow>
                  <boxGeometry args={[0.9, 0.05, 0.38]} />
                  <meshStandardMaterial color="#b8c2cf" />
                </mesh>
              );
            })}
            {showLabels && <Label3D text={op.label} color="#fde68a" bg="#451a03d9" position={[cx, y0 + rise + 0.5, cz]} />}
          </group>
        );
      })}
    </group>
  );
}

// ---------------------------------------------------------------- things in the scene

function Furniture({ layout, touched, effects, showLabels, selectedId, maxLevel, onInspect }: {
  layout: Layout; touched: Set<string>; effects: Record<string, string>; showLabels: boolean; selectedId: string | null; maxLevel: number | null; onInspect: (i: InspectedItem) => void;
}) {
  const roomY = (id: string) => layout.rooms.find((r) => r.id === id)?.floor_y ?? 0;
  const level = (id: string) => layout.rooms.find((r) => r.id === id)?.level ?? 0;
  const items = [
    ...layout.fixtures.filter((f) => maxLevel === null || level(f.room) <= maxLevel).map((f) => ({ f, kind: inferKind(f.category, f.label), y: roomY(f.room), outdoor: false })),
    ...layout.outdoor_objects.map((f) => ({ f, kind: inferKind("", f.label, f.kind), y: 0, outdoor: true })),
  ];
  return (
    <group>
      {items.map(({ f, kind, y, outdoor }) => {
        const hot = touched.has(f.id) || layout.key_locations.some((k) => k.on_fixture === f.id && touched.has(k.id));
        const moved = effects[f.id] === "disturbed" || effects[f.id] === "moved" || effects[f.id] === "damaged";
        const sel = selectedId === f.id;
        return (
          <group
            key={f.id} position={[f.pos[0], y, f.pos[2]]} rotation={moved ? [0.12, 0.2, 0.18] : [0, 0, 0]}
            onClick={(e) => {
              e.stopPropagation();
              const fx = f as (typeof layout.fixtures)[number];
              onInspect({
                id: f.id, nodeKind: outdoor ? "outdoor_object" : "fixture", title: f.label,
                kind: `${outdoor ? "Outdoor object" : "Furniture / object"} (${f.footprint_m[0].toFixed(1)} x ${f.footprint_m[1].toFixed(1)} m, ${f.height_m.toFixed(1)} m high)`, basis: f.basis,
                description: `Size and position come from the layout estimate.${!outdoor && fx.adjusted ? " " + fx.adjust_notes.join("; ") + "." : ""}${f.reachable ? "" : " Cannot be reached."}${hot ? " Someone handles it at this point in the scenario." : ""}${moved ? " Shown disturbed, as the scenario says." : ""}`,
                refs: f.evidence_refs, focus: f.pos,
              });
            }}
          >
            <FurnitureModel kind={kind} w={f.footprint_m[0]} d={f.footprint_m[1]} h={f.height_m} color={f.color_hex} hot={hot || sel} assumed={f.basis === "assumed"} />
            {(showLabels || hot || sel) && <Label3D text={f.label} color="#e2e8f0" bg="#0b1020d9" position={[0, f.height_m + 0.45, 0]} />}
          </group>
        );
      })}
    </group>
  );
}

function KeyPlaces({ layout, activeLabels, showLabels, maxLevel, onInspect }: { layout: Layout; activeLabels: Set<string>; showLabels: boolean; maxLevel: number | null; onInspect: (i: InspectedItem) => void }) {
  return (
    <group>
      {layout.key_locations.filter((k) => k.room === "outside" || maxLevel === null || (layout.rooms.find((r) => r.id === k.room)?.level ?? 0) <= maxLevel).map((kl) => {
        const y = kl.room === "outside" ? 0 : layout.rooms.find((r) => r.id === kl.room)?.floor_y ?? 0;
        const active = activeLabels.has(kl.label);
        return (
          <group
            key={kl.id} position={[kl.pos[0], y, kl.pos[2]]}
            onClick={(e) => {
              e.stopPropagation();
              onInspect({ id: kl.id, nodeKind: "key_location", title: kl.label, kind: "Place where evidence says something happened", basis: kl.basis, description: kl.significance || "No description given.", refs: kl.evidence_refs, focus: kl.pos });
            }}
          >
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
              <ringGeometry args={[0.32, 0.45, 28]} />
              <meshBasicMaterial color={active ? "#ef4444" : "#fbbf24"} transparent opacity={active ? 0.95 : 0.6} side={THREE.DoubleSide} />
            </mesh>
            {(showLabels || active) && <Label3D text={kl.label} color="#fcd34d" bg="#451a03d9" position={[0, 0.25, 0]} />}
          </group>
        );
      })}
    </group>
  );
}

function Observers({ layout, inside, showLabels, selectedId, maxLevel, onInspect }: { layout: Layout; inside: string | null; showLabels: boolean; selectedId: string | null; maxLevel: number | null; onInspect: (i: InspectedItem) => void }) {
  return (
    <group>
      {layout.observers.filter((o) => maxLevel === null || o.level <= maxLevel).map((ob) => {
        const y = ob.room === "outside" ? 0 : layout.rooms.find((r) => r.id === ob.room)?.floor_y ?? 0;
        const color = ob.kind === "camera" ? "#3b82f6" : "#a855f7";
        const fov = (Math.min(ob.fov_deg, 360) * Math.PI) / 180;
        const range = Math.min(ob.range_m, 16);
        const hidden = inside === ob.id; // the view from this camera must not be blocked by its own marker
        return (
          <group
            key={ob.id}
            onClick={(e) => {
              e.stopPropagation();
              onInspect({ id: ob.id, nodeKind: "observer", title: ob.label, kind: `${ob.kind === "camera" ? "Camera" : "Witness position"} (sees ${ob.fov_deg.toFixed(0)}° up to ${ob.range_m.toFixed(0)} m)`,
                basis: ob.basis, description: "The shaded area shows what this position can see, if nothing blocks the view. Claimed sightings are checked against walls and furniture.", refs: ob.evidence_refs, focus: ob.pos });
            }}
          >
            {!hidden && <mesh rotation={[-Math.PI / 2, 0, 0]} position={[ob.pos[0], y + 0.03, ob.pos[2]]}>
              <circleGeometry args={[range, 40, ob.yaw - Math.PI / 2 - fov / 2, fov]} />
              <meshBasicMaterial color={color} transparent opacity={0.1} side={THREE.DoubleSide} depthWrite={false} />
            </mesh>}
            {hidden ? null : ob.kind === "camera" ? (
              <group position={[ob.pos[0], y + ob.eye_height_m, ob.pos[2]]} rotation={[0, ob.yaw, 0]}>
                <mesh castShadow><boxGeometry args={[0.18, 0.14, 0.3]} /><meshStandardMaterial color="#1e293b" /></mesh>
                <mesh position={[0, 0, 0.17]} rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[0.05, 0.05, 0.06, 12]} /><meshStandardMaterial color="#60a5fa" emissive="#2563eb" emissiveIntensity={0.7} /></mesh>
              </group>
            ) : (
              <mesh position={[ob.pos[0], y + 0.05, ob.pos[2]]} rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[0.3, 0.42, 20]} /><meshBasicMaterial color={color} /></mesh>
            )}
            {!hidden && (showLabels || selectedId === ob.id) && <Label3D text={ob.label} color={color} bg="#0b1020e6" position={[ob.pos[0], y + (ob.kind === "camera" ? ob.eye_height_m + 0.45 : 0.6), ob.pos[2]]} />}
          </group>
        );
      })}
    </group>
  );
}

// ---------------------------------------------------------------- routes

function RouteLines({ scenario, sim, topY, onInspect }: { scenario: Scenario; sim: SimState; topY: number; onInspect: (i: InspectedItem) => void }) {
  const legs = useMemo(() => {
    const out: { a: Vec3; b: Vec3; seg: number; actor: string; color: string; auto: boolean; failed: boolean; label: string; notes: string[]; refs: string[] }[] = [];
    for (const a of scenario.plan.actors) {
      a.segments.forEach((s, si) => {
        if (s.kind !== "transit" || !s.route) return;
        for (let i = 0; i < s.route.length - 1; i++) {
          if (s.leg_kinds?.[i] === "stairs") continue;
          out.push({ a: s.route[i], b: s.route[i + 1], seg: si, actor: a.id, color: a.color, auto: s.auto_routed, failed: s.failed, label: s.label, notes: s.routing_notes, refs: a.steps.find((st) => st.k === s.step)?.evidence_refs ?? [] });
        }
      });
    }
    return out;
  }, [scenario]);
  const cur = new Map(sim.actors.map((a) => [a.id, a.segIndex]));
  return (
    <group>
      {legs.map((leg, i) => {
        const dx = leg.b[0] - leg.a[0];
        const dz = leg.b[2] - leg.a[2];
        const len = Math.hypot(dx, dz);
        if (len < 0.02 || Math.min(leg.a[1], leg.b[1]) > topY) return null;
        const current = cur.get(leg.actor) === leg.seg;
        return (
          <mesh
            key={i} position={[(leg.a[0] + leg.b[0]) / 2, leg.a[1] + 0.04 + (leg.auto ? 0.005 : 0), (leg.a[2] + leg.b[2]) / 2]} rotation={[0, Math.atan2(dx, dz), 0]}
            onClick={(e) => {
              e.stopPropagation();
              onInspect({ nodeKind: "route", title: `Route to ${leg.label}`, kind: leg.auto ? "Walking route (system-routed)" : "Walking route (direct)", basis: "derived",
                description: leg.notes.length ? "The system adjusted this route: " + leg.notes.join("; ") + "." : "Straight walk between the two places named in the scenario.", refs: leg.refs });
            }}
          >
            <boxGeometry args={[current ? 0.13 : 0.07, 0.02, len]} />
            <meshBasicMaterial color={leg.failed ? "#ef4444" : leg.color} transparent opacity={current ? 1 : leg.auto ? 0.75 : 0.5} />
          </mesh>
        );
      })}
    </group>
  );
}

function OverlayRoutes({ scenarios, topY }: { scenarios: Scenario[]; topY: number }) {
  return (
    <group>
      {scenarios.map((s, si) =>
        s.plan.actors.flatMap((a) =>
          a.segments.filter((sg) => sg.kind === "transit" && sg.route).flatMap((sg, k) =>
            (sg.route ?? []).slice(0, -1).map((p, i) => {
              const q = (sg.route ?? [])[i + 1];
              if (sg.leg_kinds?.[i] === "stairs") return null;
              const dx = q[0] - p[0];
              const dz = q[2] - p[2];
              const len = Math.hypot(dx, dz);
              if (len < 0.02 || Math.min(p[1], q[1]) > topY) return null;
              return (
                <mesh key={`${s.scenario_id}-${a.id}-${k}-${i}`} position={[(p[0] + q[0]) / 2, p[1] + 0.06 + si * 0.012, (p[2] + q[2]) / 2]} rotation={[0, Math.atan2(dx, dz), 0]}>
                  <boxGeometry args={[0.05, 0.015, len]} />
                  <meshBasicMaterial color={OVERLAY_COLORS[si % OVERLAY_COLORS.length]} transparent opacity={0.85} />
                </mesh>
              );
            }),
          ),
        ),
      )}
    </group>
  );
}

// ---------------------------------------------------------------- people

const angleDiff = (a: number, b: number) => ((b - a + Math.PI * 3) % (Math.PI * 2)) - Math.PI;

function Person({ actor, visible }: { actor: ActorState; visible: boolean }) {
  const root = useRef<THREE.Group>(null);
  const body = useRef<THREE.Group>(null);
  const head = useRef<THREE.Mesh>(null);
  const lArm = useRef<THREE.Group>(null);
  const rArm = useRef<THREE.Group>(null);
  const lLeg = useRef<THREE.Group>(null);
  const rLeg = useRef<THREE.Group>(null);
  const yaw = useRef<number | null>(null);
  const clothes = actor.color;
  const faded = useRef<boolean | null>(null);

  useFrame((_, delta) => {
    if (!root.current) return;
    root.current.visible = visible;
    // before their first step and after their last, the evidence does not say where they are: shown as a faint ghost, not as if still acting
    const ghost = !actor.started || actor.ended;
    if (faded.current !== ghost) {
      faded.current = ghost;
      root.current.traverse((o) => {
        const m = (o as THREE.Mesh).material as THREE.Material | THREE.Material[] | undefined;
        for (const mat of Array.isArray(m) ? m : m ? [m] : []) {
          const keep = (mat.userData as { base?: number }).base ?? mat.opacity;
          (mat.userData as { base?: number }).base = keep;
          mat.transparent = ghost || keep < 1;
          mat.opacity = ghost ? Math.min(keep, 0.22) : keep;
          mat.needsUpdate = true;
        }
      });
    }
    root.current.position.set(actor.pos[0], actor.pos[1], actor.pos[2]);
    if (yaw.current === null) yaw.current = actor.heading;
    yaw.current += angleDiff(yaw.current, actor.heading) * (1 - Math.exp(-delta * 10)); // turns over ~0.1-0.2 s at any frame rate
    root.current.rotation.y = yaw.current;
    const walking = actor.pose === "walk" || actor.pose === "run";
    const cyc = Math.sin((actor.travelled * Math.PI * 2) / 1.4);
    const amp = walking ? (actor.pose === "run" ? 0.85 : 0.5) * Math.min(1, actor.speed / 0.6) : 0;
    let ll = cyc * amp, rl = -cyc * amp;
    let la = walking ? -cyc * amp * 0.8 : 0, ra = walking ? cyc * amp * 0.8 : 0;
    let lean = actor.pose === "run" ? 0.2 : 0, headYaw = 0, drop = 0, lie = false;
    const t = performance.now() / 1000;
    switch (actor.pose) {
      case "look": headYaw = Math.sin(t * 1.6) * 0.7; la = -0.25; ra = -0.25; break;
      case "reach": lean = 0.3; ra = -1.3 + Math.sin(t * 2.5) * 0.12; la = -0.2; break;
      case "struggle": lean = 0.2; la = -1.0 + Math.sin(t * 7) * 0.5; ra = -1.0 - Math.sin(t * 7) * 0.5; break;
      case "call": ra = -2.5; headYaw = 0.25; break;
      case "crouch": drop = 0.4; lean = 0.4; ll = -0.9; rl = -0.9; break;
      case "sit": drop = 0.42; ll = -1.45; rl = -1.45; la = -0.4; ra = -0.4; break;
      case "lie": lie = true; break;
      default: break;
    }
    if (lLeg.current && rLeg.current) {
      lLeg.current.rotation.x = ll;
      rLeg.current.rotation.x = rl;
      lLeg.current.position.y = rLeg.current.position.y = 0.9 - drop;
    }
    if (lArm.current && rArm.current) { lArm.current.rotation.x = la; rArm.current.rotation.x = ra; }
    if (body.current) {
      body.current.rotation.x = lie ? -Math.PI / 2 : lean;
      body.current.position.set(0, lie ? 0.16 : 0.9 - drop, lie ? -0.9 : 0);
    }
    if (head.current) head.current.rotation.y = headYaw;
  });

  return (
    <group ref={root}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}><circleGeometry args={[0.32, 24]} /><meshBasicMaterial color="#000" transparent opacity={0.35} /></mesh>
      <group ref={lLeg} position={[-0.11, 0.9, 0]}><mesh position={[0, -0.45, 0]} castShadow><capsuleGeometry args={[0.07, 0.7, 4, 8]} /><meshStandardMaterial color="#1e293b" /></mesh></group>
      <group ref={rLeg} position={[0.11, 0.9, 0]}><mesh position={[0, -0.45, 0]} castShadow><capsuleGeometry args={[0.07, 0.7, 4, 8]} /><meshStandardMaterial color="#1e293b" /></mesh></group>
      <group ref={body} position={[0, 0.9, 0]}>
        <mesh position={[0, 0.32, 0]} castShadow><capsuleGeometry args={[0.2, 0.42, 6, 12]} /><meshStandardMaterial color={clothes} /></mesh>
        <mesh ref={head} position={[0, 0.82, 0]} castShadow>
          <sphereGeometry args={[0.13, 16, 16]} /><meshStandardMaterial color="#d4a98a" />
          <mesh position={[0, -0.01, 0.12]}><boxGeometry args={[0.07, 0.03, 0.04]} /><meshStandardMaterial color="#7c5a44" /></mesh>
        </mesh>
        <group ref={lArm} position={[-0.27, 0.58, 0]}><mesh position={[0, -0.27, 0]} castShadow><capsuleGeometry args={[0.055, 0.42, 4, 8]} /><meshStandardMaterial color={clothes} /></mesh></group>
        <group ref={rArm} position={[0.27, 0.58, 0]}>
          <mesh position={[0, -0.27, 0]} castShadow><capsuleGeometry args={[0.055, 0.42, 4, 8]} /><meshStandardMaterial color={clothes} /></mesh>
          {actor.carrying && <mesh position={[0.02, -0.55, 0.08]}><boxGeometry args={[0.16, 0.16, 0.16]} /><meshStandardMaterial color="#9ca3af" /></mesh>}
        </group>
      </group>
    </group>
  );
}

const shortName = (n: string) => (n.length > 18 ? n.slice(0, 17).trimEnd() + "…" : n);

function PeopleLabels({ actors, show }: { actors: ActorState[]; show: boolean }) {
  if (!show) return null;
  return (
    <group>
      {actors.map((a) => (
        <group key={a.id}>
          <Label3D text={!a.started ? `${shortName(a.label)} (not yet shown)` : a.ended ? `${shortName(a.label)} (last known)` : a.label} color={a.color} bg="#0b1020e6" position={[a.pos[0], a.pos[1] + (a.pose === "lie" ? 0.6 : 2.15), a.pos[2]]} />
          {a.carrying && a.item && a.started && !a.ended && <Label3D text={`carrying: ${a.item}`} color="#e5e7eb" bg="#111827e6" position={[a.pos[0], a.pos[1] + (a.pose === "lie" ? 0.95 : 2.5), a.pos[2]]} />}
        </group>
      ))}
    </group>
  );
}

// ---------------------------------------------------------------- the scene

export interface SceneProps {
  layout: Layout;
  scenario?: Scenario;
  overlay: Scenario[];
  sim: SimState;
  cutaway: boolean;
  showLabels: boolean;
  camera: CameraMode;
  focus: Vec3 | null;
  selectedId: string | null;
  maxLevel: number | null;
  daylight: number;
  dragMode: "rotate" | "move";
  onInspect: (i: InspectedItem) => void;
}

const CANVAS_STYLE = { width: "100%", height: "100%" } as const;

export default function SandboxScene3D(p: SceneProps) {
  const { layout, scenario, sim } = p;
  const touched = useMemo(() => new Set(sim.touchedNodeIds), [sim.touchedNodeIds]);
  const activeLabels = useMemo(() => new Set(sim.actors.filter((a) => a.kind === "dwell").map((a) => a.placeLabel)), [sim.actors]);
  const forcedLater = useMemo(() => new Set((scenario?.plan.effects ?? []).filter((e) => e.state === "forced").map((e) => e.target)), [scenario]);
  // routes on floors hidden by the floor filter are hidden too
  const topY = p.maxLevel === null ? Infinity : Math.max(...layout.levels.filter((l) => l.level <= p.maxLevel!).map((l) => l.floor_y + l.height_m), 0);
  const b = useMemo(() => bounds(layout), [layout]);
  const cam = useMemo(() => ({ position: [b.cx + b.diag * 0.7, b.diag * 0.88, b.cz - b.diag * 0.95] as Vec3, fov: 46 }), [b]);
  const levelOf = (space: string) => layout.rooms.find((r) => r.id === space)?.level ?? 0;
  const day = p.daylight;
  return (
    <Canvas camera={cam} style={CANVAS_STYLE} shadows>
      <color attach="background" args={[day > 0.5 ? "#0f1626" : "#050914"]} />
      <ambientLight intensity={0.3 + 0.6 * day} color={day > 0.5 ? "#ffffff" : "#8ea3ff"} />
      <directionalLight position={[b.cx + 10, 22, b.cz - 8]} intensity={0.25 + 0.9 * day} castShadow shadow-mapSize={[1024, 1024]} shadow-camera-left={-b.diag} shadow-camera-right={b.diag} shadow-camera-top={b.diag} shadow-camera-bottom={-b.diag} />
      <directionalLight position={[b.cx - 8, 10, b.cz + 8]} intensity={0.2 + 0.3 * day} />
      <CameraRig layout={layout} mode={p.camera} sim={sim} focus={p.focus} dragMode={p.dragMode} />
      <Ground layout={layout} />
      {layout.rooms.filter((r) => p.maxLevel === null || r.level <= p.maxLevel).map((r) => <Floor key={r.id} room={r} hole={stairHole(layout, r)} onInspect={p.onInspect} />)}
      <Shell layout={layout} cutaway={p.cutaway} maxLevel={p.maxLevel} onInspect={p.onInspect} />
      <Doors layout={layout} state={sim.effectStates} forcedLater={forcedLater} showLabels={p.showLabels} selectedId={p.selectedId} actors={sim.actors} maxLevel={p.maxLevel} onInspect={p.onInspect} />
      <Stairs layout={layout} maxLevel={p.maxLevel} showLabels={p.showLabels} onInspect={p.onInspect} />
      <Furniture layout={layout} touched={touched} effects={sim.effectStates} showLabels={p.showLabels} selectedId={p.selectedId} maxLevel={p.maxLevel} onInspect={p.onInspect} />
      <KeyPlaces layout={layout} activeLabels={activeLabels} showLabels={p.showLabels} maxLevel={p.maxLevel} onInspect={p.onInspect} />
      <Observers layout={layout} showLabels={p.showLabels} selectedId={p.selectedId} inside={p.camera.startsWith("observer:") ? p.camera.slice(9) : null} maxLevel={p.maxLevel} onInspect={p.onInspect} />
      {scenario && <RouteLines scenario={scenario} sim={sim} topY={topY} onInspect={p.onInspect} />}
      {p.overlay.length > 0 && <OverlayRoutes scenarios={p.overlay} topY={topY} />}
      {scenario && sim.actors.map((a) => <Person key={a.id} actor={a} visible={p.maxLevel === null || levelOf(a.space) <= p.maxLevel} />)}
      {scenario && <PeopleLabels actors={sim.actors.filter((a) => p.maxLevel === null || levelOf(a.space) <= p.maxLevel)} show />}
    </Canvas>
  );
}
