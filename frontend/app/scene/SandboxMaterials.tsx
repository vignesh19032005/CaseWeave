"use client";

// Physically based materials for the scene, with no downloads: the surface detail (grain, brushing, concrete, plaster) is generated once as
// small grey-scale maps, and a soft built-in studio environment lets metal and glossy surfaces reflect something. Colours still come from the
// layout, and anything the evidence does not describe keeps its red outline, so nothing here adds detail the case does not have.
import React, { createContext, useContext, useEffect, useMemo } from "react";
import * as THREE from "three";
import { useThree } from "@react-three/fiber";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

export type Finish = "wood" | "steel" | "paint" | "plain";

function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function canvasTex(size: number, draw: (g: CanvasRenderingContext2D, r: () => number) => void, seed: number): THREE.CanvasTexture | null {
  if (typeof document === "undefined") return null;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  if (!g) return null;
  draw(g, rng(seed));
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 4;
  return t;
}

interface Maps { concrete: THREE.CanvasTexture | null; plaster: THREE.CanvasTexture | null; grain: THREE.CanvasTexture | null; brushed: THREE.CanvasTexture | null; rough: THREE.CanvasTexture | null }
let cache: Maps | null = null;

function maps(): Maps {
  if (cache) return cache;
  const S = 256;
  const concrete = canvasTex(S, (g, r) => {
    g.fillStyle = "#808080"; g.fillRect(0, 0, S, S);
    for (let i = 0; i < 2600; i++) { const v = 90 + r() * 90; g.fillStyle = `rgba(${v},${v},${v},${0.12 + r() * 0.25})`; const s = 1 + r() * 4; g.fillRect(r() * S, r() * S, s, s); }
  }, 11);
  const plaster = canvasTex(S, (g, r) => {
    g.fillStyle = "#909090"; g.fillRect(0, 0, S, S);
    for (let i = 0; i < 900; i++) { const v = 110 + r() * 70; g.fillStyle = `rgba(${v},${v},${v},0.18)`; g.beginPath(); g.arc(r() * S, r() * S, 2 + r() * 9, 0, 6.3); g.fill(); }
  }, 23);
  const grain = canvasTex(S, (g, r) => {
    g.fillStyle = "#8a8a8a"; g.fillRect(0, 0, S, S);
    for (let y = 0; y < S; y += 1) { const base = 120 + Math.sin(y * 0.35 + r() * 0.6) * 38 + (r() - 0.5) * 34; g.fillStyle = `rgb(${base},${base},${base})`; g.fillRect(0, y, S, 1); }
    for (let i = 0; i < 30; i++) { g.strokeStyle = `rgba(60,60,60,${0.2 + r() * 0.3})`; g.beginPath(); const y = r() * S; g.moveTo(0, y); g.bezierCurveTo(S * 0.3, y + (r() - 0.5) * 8, S * 0.6, y + (r() - 0.5) * 8, S, y + (r() - 0.5) * 6); g.stroke(); }
  }, 37);
  const brushed = canvasTex(S, (g, r) => {
    g.fillStyle = "#909090"; g.fillRect(0, 0, S, S);
    for (let y = 0; y < S; y++) { const v = 105 + r() * 90; g.fillStyle = `rgba(${v},${v},${v},0.9)`; g.fillRect(0, y, S, 1); }
  }, 41);
  const rough = canvasTex(S, (g, r) => {
    g.fillStyle = "#b0b0b0"; g.fillRect(0, 0, S, S);
    for (let i = 0; i < 1800; i++) { const v = 150 + r() * 80; g.fillStyle = `rgba(${v},${v},${v},0.2)`; g.fillRect(r() * S, r() * S, 2 + r() * 6, 2 + r() * 6); }
  }, 53);
  cache = { concrete, plaster, grain, brushed, rough };
  return cache;
}

/** A copy of a shared map with its own repeat, so big surfaces get fine detail instead of one stretched picture. */
export function repeated(t: THREE.CanvasTexture | null, x: number, y: number): THREE.Texture | null {
  if (!t) return null;
  const c = t.clone();
  c.repeat.set(Math.max(1, x), Math.max(1, y));
  c.needsUpdate = true;
  return c;
}

// ---------------------------------------------------------------- surfaces

export function FloorMaterial({ map, w, l, color = "#ffffff" }: { map?: THREE.Texture | null; w: number; l: number; color?: string }) {
  const m = maps();
  const bump = useMemo(() => repeated(m.concrete, w / 1.5, l / 1.5), [m.concrete, w, l]);
  const rough = useMemo(() => repeated(m.rough, w / 2, l / 2), [m.rough, w, l]);
  useEffect(() => () => { bump?.dispose(); rough?.dispose(); }, [bump, rough]);
  return <meshStandardMaterial map={map ?? null} color={color} roughness={0.55} roughnessMap={rough} metalness={0.05} bumpMap={bump} bumpScale={0.6} />;
}

export function WallMaterial({ w, h, cutaway }: { w: number; h: number; cutaway: boolean }) {
  const m = maps();
  const bump = useMemo(() => repeated(m.plaster, Math.max(1, w / 2), Math.max(1, h / 2)), [m.plaster, w, h]);
  useEffect(() => () => bump?.dispose(), [bump]);
  return <meshStandardMaterial color="#5b6b82" roughness={0.88} metalness={0} bumpMap={bump} bumpScale={0.5} transparent={cutaway} opacity={cutaway ? 0.95 : 1} />;
}

const FinishCtx = createContext<Finish>("plain");
export const FinishProvider = FinishCtx.Provider;

/** The material a piece of furniture is made of: grained wood, brushed steel, glossy paint, or plain. */
export function FinishMaterial({ color, rough = 0.65 }: { color: string; rough?: number }) {
  const finish = useContext(FinishCtx);
  const m = maps();
  const grain = useMemo(() => (finish === "wood" ? repeated(m.grain, 2, 1) : finish === "steel" ? repeated(m.brushed, 1, 3) : null), [finish, m.grain, m.brushed]);
  useEffect(() => () => grain?.dispose(), [grain]);
  if (finish === "steel") return <meshStandardMaterial color={color} metalness={0.85} roughness={0.38} roughnessMap={grain} bumpMap={grain} bumpScale={0.25} />;
  if (finish === "wood") return <meshStandardMaterial color={color} metalness={0} roughness={Math.min(0.85, rough + 0.1)} roughnessMap={grain} bumpMap={grain} bumpScale={0.7} />;
  if (finish === "paint") return <meshStandardMaterial color={color} metalness={0.55} roughness={0.32} />;
  return <meshStandardMaterial color={color} roughness={rough} metalness={0} />;
}

// ---------------------------------------------------------------- the soft studio the metal reflects

function applyEnvironment(scene: THREE.Scene, tex: THREE.Texture | null, intensity?: number) {
  scene.environment = tex;
  if (intensity !== undefined) scene.environmentIntensity = intensity;
}

export function SceneEnvironment({ daylight }: { daylight: number }) {
  const { gl, scene } = useThree();
  const target = useMemo(() => {
    const pm = new THREE.PMREMGenerator(gl);
    const env = new RoomEnvironment();
    const rt = pm.fromScene(env, 0.04);
    pm.dispose();
    return rt;
  }, [gl]);
  useEffect(() => {
    applyEnvironment(scene, target.texture);
    return () => { applyEnvironment(scene, null); target.dispose(); };
  }, [scene, target]);
  useEffect(() => {
    applyEnvironment(scene, scene.environment, 0.04 + 0.22 * daylight);   // dimmer at night, so a night scene still looks like night
  }, [scene, daylight]);
  return null;
}
