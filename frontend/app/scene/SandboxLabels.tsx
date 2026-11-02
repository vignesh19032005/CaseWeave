"use client";

// Labels that do not hide the scene. Every label registers where it points in the world; once per frame a layout pass projects them all to
// the screen and places them by priority (people and the selected object first, then the active place, then the rest), away from the
// bodies of people and from each other, with a thin leader line back to what they name. Labels that cannot be placed without covering
// something are hidden unless they are top priority. While you drag the view, everything except the selected object fades out.
import React, { createContext, useContext, useEffect, useId, useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame, useThree } from "@react-three/fiber";
import type { Vec3 } from "./sandboxTypes";

export type LabelMode = "off" | "minimal" | "all";

const LABEL_SCREEN_HEIGHT = 0.02;
const MAX_CHARS = 34;

export const labelState = { dragging: false };

export interface LabelSpec {
  text: string;
  color: string;
  bg: string;
  priority: 0 | 1 | 2; // 0 people and the selected object, 1 the active place, 2 everything else
  body?: number; // metres below the anchor that must stay uncovered (a person's body)
}
interface Entry { ref: React.RefObject<THREE.Object3D | null>; spec: LabelSpec }
interface Api { register: (id: string, e: Entry) => void; unregister: (id: string) => void }

const Ctx = createContext<Api | null>(null);

// ---------------------------------------------------------------- the picture of one label

const textures = new Map<string, { tex: THREE.CanvasTexture; aspect: number }>();
function labelTexture(text: string, color: string, bg: string) {
  const key = `${text}|${color}|${bg}`;
  const hit = textures.get(key);
  if (hit) return hit;
  const c = document.createElement("canvas");
  const ctx = c.getContext("2d");
  if (!ctx) return null;
  const font = "600 30px system-ui, sans-serif";
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
  const made = { tex, aspect: w / 52 };
  textures.set(key, made);
  if (textures.size > 400) {
    const first = textures.keys().next().value;
    if (first !== undefined) {
      textures.get(first)?.tex.dispose();
      textures.delete(first);
    }
  }
  return made;
}

// ---------------------------------------------------------------- what a scene part uses

export function Label3D({ text: full, color, bg, position, priority = 2, body }: { text: string; color: string; bg: string; position: Vec3; priority?: 0 | 1 | 2; body?: number }) {
  const api = useContext(Ctx);
  const id = useId();
  const ref = useRef<THREE.Object3D>(null);
  const text = full.length > MAX_CHARS ? full.slice(0, MAX_CHARS - 1).trimEnd() + "…" : full;
  useEffect(() => {
    if (!api) return;
    api.register(id, { ref, spec: { text, color, bg, priority, body } });
    return () => api.unregister(id);
  }, [api, id, text, color, bg, priority, body]);
  return <object3D ref={ref} position={position} />;
}

// ---------------------------------------------------------------- the layout pass

interface Item { sprite: THREE.Sprite; line: THREE.Line; key: string; cx: number; cy: number; opacity: number; seen: boolean }
interface Box { x0: number; y0: number; x1: number; y1: number }

// scratch vectors, reused every frame
const SV = new THREE.Vector3();
const SW = new THREE.Vector3();
const SU = new THREE.Vector3();

const hit = (a: Box, b: Box, pad = 2) => a.x0 < b.x1 + pad && a.x1 > b.x0 - pad && a.y0 < b.y1 + pad && a.y1 > b.y0 - pad;

function LabelRenderer({ reg, muted }: { reg: React.MutableRefObject<Map<string, Entry>>; muted: boolean }) {
  const { camera, size, scene } = useThree();
  const pool = useRef(new Map<string, Item>());

  useEffect(() => {
    const items = pool.current;
    return () => {
      items.forEach((it) => {
        scene.remove(it.sprite);
        scene.remove(it.line);
        it.sprite.material.dispose();
        it.line.geometry.dispose();
        (it.line.material as THREE.Material).dispose();
      });
      items.clear();
    };
  }, [scene]);

  useFrame((_, delta) => {
    const cam = camera as THREE.PerspectiveCamera;
    const w = size.width;
    const h = size.height;
    const perspective = (cam as THREE.PerspectiveCamera).isPerspectiveCamera;
    const Hpx = LABEL_SCREEN_HEIGHT * h * (perspective ? 1 / (2 * Math.tan((cam.fov * Math.PI) / 360)) : 1);
    type Row = { id: string; e: Entry; px: number; py: number; z: number; tex: NonNullable<ReturnType<typeof labelTexture>> };
    const rows: Row[] = [];
    const live = new Set<string>();
    reg.current.forEach((e, id) => {
      const o = e.ref.current;
      if (!o) return;
      o.getWorldPosition(SV);
      SW.copy(SV).project(cam);
      if (SW.z > 1 || SW.z < -1 || Math.abs(SW.x) > 1.15 || Math.abs(SW.y) > 1.15) return;
      const tex = labelTexture(e.spec.text, e.spec.color, e.spec.bg);
      if (!tex) return;
      rows.push({ id, e, px: (SW.x * 0.5 + 0.5) * w, py: (1 - (SW.y * 0.5 + 0.5)) * h, z: SW.z, tex });
      live.add(id);
    });
    // bodies that must stay uncovered
    const obstacles: Box[] = [];
    for (const r of rows) {
      if (!r.e.spec.body) continue;
      const o = r.e.ref.current as THREE.Object3D;
      o.getWorldPosition(SV);
      SV.y -= r.e.spec.body;
      SW.copy(SV).project(cam);
      const by = (1 - (SW.y * 0.5 + 0.5)) * h;
      const bx = (SW.x * 0.5 + 0.5) * w;
      const halfW = Math.max(9, Math.abs(by - r.py) * 0.22);
      obstacles.push({ x0: Math.min(bx, r.px) - halfW, x1: Math.max(bx, r.px) + halfW, y0: Math.min(by, r.py), y1: Math.max(by, r.py) });
    }
    rows.sort((a, b) => a.e.spec.priority - b.e.spec.priority || a.z - b.z);
    const placed: Box[] = [];
    const seen = new Set<string>();
    const debug = typeof window !== "undefined" && (window as unknown as { __cwLabelDebug?: boolean }).__cwLabelDebug ? [] as { text: string; priority: number; visible: boolean; box: Box }[] : null;
    for (const r of rows) {
      let it = pool.current.get(r.id);
      if (!it || it.key !== `${r.e.spec.text}|${r.e.spec.color}|${r.e.spec.bg}`) {
        if (it) {
          scene.remove(it.sprite);
          scene.remove(it.line);
          it.sprite.material.dispose();
          it.line.geometry.dispose();
          (it.line.material as THREE.Material).dispose();
        }
        const mat = new THREE.SpriteMaterial({ map: r.tex.tex, transparent: true, depthTest: false, depthWrite: false, sizeAttenuation: false });
        const sprite = new THREE.Sprite(mat);
        sprite.renderOrder = 20;
        sprite.raycast = () => null;
        sprite.frustumCulled = false;
        const geo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
        const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: r.e.spec.color, transparent: true, opacity: 0.7, depthTest: false }));
        line.renderOrder = 19;
        line.frustumCulled = false;
        line.raycast = () => null;
        scene.add(sprite);
        scene.add(line);
        it = { sprite, line, key: `${r.e.spec.text}|${r.e.spec.color}|${r.e.spec.bg}`, cx: r.px, cy: r.py - Hpx * 1.5, opacity: 0, seen: false };
        pool.current.set(r.id, it);
      }
      const bw = Hpx * r.tex.aspect;
      const bh = Hpx;
      const side = bw * 0.5 + 10;
      const candidates: [number, number][] = [[0, -1.5 * bh], [0, -2.8 * bh], [side, -1.3 * bh], [-side, -1.3 * bh], [0, -4.2 * bh], [side, -2.8 * bh], [-side, -2.8 * bh], [side, 0.2 * bh], [-side, 0.2 * bh], [0, 1.6 * bh], [0, -5.6 * bh]];
      let chosen: [number, number] | null = null;
      for (const [dx, dy] of candidates) {
        const cx = Math.min(w - bw / 2 - 2, Math.max(bw / 2 + 2, r.px + dx));
        const cy = Math.min(h - bh / 2 - 2, Math.max(bh / 2 + 2, r.py + dy));
        const box = { x0: cx - bw / 2, x1: cx + bw / 2, y0: cy - bh / 2, y1: cy + bh / 2 };
        if (!placed.some((p) => hit(p, box)) && !obstacles.some((o) => hit(o, box, 0))) {
          chosen = [cx, cy];
          placed.push(box);
          break;
        }
      }
      let visible = true;
      if (!chosen) {
        if (r.e.spec.priority === 0) {
          chosen = [r.px, r.py - 1.5 * bh];
          placed.push({ x0: chosen[0] - bw / 2, x1: chosen[0] + bw / 2, y0: chosen[1] - bh / 2, y1: chosen[1] + bh / 2 });
        } else {
          chosen = [it.cx, it.cy];
          visible = false;
        }
      }
      if (debug) debug.push({ text: r.e.spec.text, priority: r.e.spec.priority, visible, box: { x0: chosen[0] - bw / 2, x1: chosen[0] + bw / 2, y0: chosen[1] - bh / 2, y1: chosen[1] + bh / 2 } });
      const k = 1 - Math.exp(-delta * 14);
      it.cx += (chosen[0] - it.cx) * k;
      it.cy += (chosen[1] - it.cy) * k;
      const target = muted || !visible ? 0 : labelState.dragging && r.e.spec.priority > 0 ? 0.08 : 1;
      it.opacity += (target - it.opacity) * (1 - Math.exp(-delta * 10));
      (it.sprite.material as THREE.SpriteMaterial).opacity = it.opacity;
      it.sprite.visible = it.opacity > 0.02;
      it.sprite.scale.set(LABEL_SCREEN_HEIGHT * r.tex.aspect, LABEL_SCREEN_HEIGHT, 1);
      SU.set((it.cx / w) * 2 - 1, 1 - (it.cy / h) * 2, r.z).unproject(cam);
      it.sprite.position.copy(SU);
      const far = Math.hypot(it.cx - r.px, it.cy - r.py) > bh * 1.1;
      const o = r.e.ref.current as THREE.Object3D;
      o.getWorldPosition(SV);
      const pos = it.line.geometry.attributes.position as THREE.BufferAttribute;
      pos.setXYZ(0, SV.x, SV.y, SV.z);
      pos.setXYZ(1, SU.x, SU.y, SU.z);
      pos.needsUpdate = true;
      (it.line.material as THREE.LineBasicMaterial).opacity = 0.7 * it.opacity;
      it.line.visible = far && it.sprite.visible;
      it.seen = true;
      seen.add(r.id);
    }
    if (debug) (window as unknown as { __cwLabels?: unknown }).__cwLabels = { labels: debug, obstacles, w, h };
    // labels that are not on screen or no longer exist
    pool.current.forEach((it, id) => {
      if (seen.has(id)) return;
      it.opacity += (0 - it.opacity) * (1 - Math.exp(-delta * 10));
      (it.sprite.material as THREE.SpriteMaterial).opacity = it.opacity;
      it.sprite.visible = it.opacity > 0.02;
      it.line.visible = false;
      if (!reg.current.has(id) && it.opacity < 0.02) {
        scene.remove(it.sprite);
        scene.remove(it.line);
        it.sprite.material.dispose();
        it.line.geometry.dispose();
        (it.line.material as THREE.Material).dispose();
        pool.current.delete(id);
      }
    });
    void live;
  });
  return null;
}

export function LabelProvider({ muted, children }: { muted: boolean; children: React.ReactNode }) {
  const reg = useRef(new Map<string, Entry>());
  const api = useMemo<Api>(() => ({ register: (id, e) => { reg.current.set(id, e); }, unregister: (id) => { reg.current.delete(id); } }), []);
  return (
    <Ctx.Provider value={api}>
      {children}
      <LabelRenderer reg={reg} muted={muted} />
    </Ctx.Provider>
  );
}
