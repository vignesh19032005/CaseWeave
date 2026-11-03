"use client";

import React, { useMemo } from "react";
import * as THREE from "three";
import { Edges, RoundedBox } from "@react-three/drei";
import { FinishMaterial, FinishProvider } from "./SandboxMaterials";
import type { Finish } from "./SandboxMaterials";
import { ModelOrFallback, modelFor } from "./SandboxModels";

// Parametric furniture: every shape is built from the object's real footprint and height,
// so it is the right size for any case. The shape is chosen from the category the model gave,
// or from words in the label; nothing here refers to a specific case.

export type FurnitureKind = "counter" | "shelf" | "cabinet" | "safe" | "desk" | "table" | "chair" | "bed" | "appliance" | "vehicle" | "tree" | "fence" | "box";

const WORDS: [RegExp, FurnitureKind][] = [
  [/counter|bench|reception|desk top|checkout|bar\b/i, "counter"],
  [/shelv|shelf|rack|stack|bookcase|storage unit/i, "shelf"],
  [/\bsafe\b|vault|strongbox/i, "safe"],
  [/cabinet|locker|cupboard|wardrobe|almirah|drawer|fridge|refrigerator|freezer/i, "cabinet"],
  [/\bdesk\b|workstation/i, "desk"],
  [/table|workbench/i, "table"],
  [/chair|stool|seat|sofa|couch|bench seat/i, "chair"],
  [/\bbed\b|mattress|cot\b/i, "bed"],
  [/machine|appliance|oven|stove|washer|printer|computer|terminal|till|register|atm/i, "appliance"],
  [/car\b|van\b|truck|vehicle|bike|motorcycle|scooter|auto\b|lorry|bus\b/i, "vehicle"],
  [/tree|bush|plant/i, "tree"],
  [/fence|wall segment|barrier|gate/i, "fence"],
];

export function inferKind(category: string, label: string, kind?: string): FurnitureKind {
  const c = (category || "").toLowerCase();
  if (kind === "vehicle" || kind === "tree" || kind === "fence") return kind;
  const direct: Record<string, FurnitureKind> = { counter: "counter", shelf: "shelf", cabinet: "cabinet", safe: "safe", locker: "cabinet", table: "table", desk: "desk", chair: "chair", bed: "bed", appliance: "appliance" };
  if (direct[c]) return direct[c];
  for (const [rx, k] of WORDS) if (rx.test(label)) return k;
  return "box";
}

function shade(hex: string, f: number): string {
  const c = new THREE.Color(hex);
  c.multiplyScalar(f);
  return `#${c.getHexString()}`;
}

function Slab({ size, pos, color, rough = 0.7 }: { size: [number, number, number]; pos: [number, number, number]; color: string; rough?: number }) {
  return (
    <mesh position={pos} castShadow receiveShadow>
      <boxGeometry args={size} />
      <FinishMaterial color={color} rough={rough} />
    </mesh>
  );
}

const FINISH_OF: Record<FurnitureKind, Finish> = { counter: "wood", shelf: "wood", cabinet: "steel", safe: "steel", desk: "wood", table: "wood", chair: "wood", bed: "plain", appliance: "steel", vehicle: "paint", tree: "plain", fence: "wood", box: "plain" };

type ModelProps = { kind: FurnitureKind; w: number; d: number; h: number; color: string; hot: boolean; assumed: boolean; label?: string };

/** The object's own material (grained wood, brushed steel, paint) with its red outline for anything the evidence does not describe. */
export function FurnitureModel(props: ModelProps) {
  const plain = (
    <FinishProvider value={FINISH_OF[props.kind]}>
      <FurnitureModelInner {...props} />
    </FinishProvider>
  );
  // A real model only for objects the evidence describes (assumed ones stay schematic with their red outline) and only when the label matches it
  const spec = props.assumed || !props.label ? null : modelFor(props.kind, props.label);
  if (!spec) return plain;
  return (
    <group>
      <ModelOrFallback spec={spec} w={props.w} d={props.d} h={props.h} fallback={plain} />
      {props.hot && <mesh position={[0, props.h / 2, 0]}><boxGeometry args={[props.w, props.h, props.d]} /><meshBasicMaterial color="#f59e0b" wireframe /></mesh>}
    </group>
  );
}

function FurnitureModelInner({ kind, w, d, h, color, hot, assumed }: ModelProps) {
  const c = hot ? "#f59e0b" : color;
  const dark = useMemo(() => shade(c, 0.6), [c]);
  const light = useMemo(() => shade(c, 1.25), [c]);
  const edge = assumed ? "#f43f5e" : "#0f172a";
  const body = (
    <RoundedBox args={[w, h, d]} radius={Math.min(0.04, Math.min(w, d, h) * 0.18)} smoothness={3} position={[0, h / 2, 0]} castShadow receiveShadow>
      <FinishMaterial color={c} rough={0.65} />
      <Edges color={edge} />
    </RoundedBox>
  );
  switch (kind) {
    case "counter":
      return (
        <group>
          <Slab size={[w, h * 0.94, d * 0.92]} pos={[0, h * 0.47, 0]} color={c} />
          <Slab size={[w + 0.06, 0.05, d + 0.1]} pos={[0, h * 0.94 + 0.025, 0.02]} color={light} rough={0.4} />
          <mesh position={[0, h / 2, 0]}><boxGeometry args={[w + 0.001, h + 0.001, d + 0.001]} /><meshBasicMaterial visible={false} /><Edges color={edge} /></mesh>
        </group>
      );
    case "shelf": {
      const boards = Math.max(3, Math.round(h / 0.42));
      return (
        <group>
          {[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([sx, sz], i) => (
            <Slab key={i} size={[0.05, h, 0.05]} pos={[(sx * (w - 0.05)) / 2, h / 2, (sz * (d - 0.05)) / 2]} color={dark} />
          ))}
          {Array.from({ length: boards }, (_, i) => (
            <Slab key={`b${i}`} size={[w, 0.035, d]} pos={[0, 0.06 + (i * (h - 0.1)) / (boards - 1), 0]} color={c} />
          ))}
          <Slab size={[w, h, 0.02]} pos={[0, h / 2, -d / 2 + 0.01]} color={dark} />
          <mesh position={[0, h / 2, 0]}><boxGeometry args={[w, h, d]} /><meshBasicMaterial visible={false} /><Edges color={edge} /></mesh>
        </group>
      );
    }
    case "cabinet":
      return (
        <group>
          {body}
          <Slab size={[0.012, h * 0.88, 0.012]} pos={[0, h * 0.5, d / 2 + 0.006]} color={dark} />
          <Slab size={[0.03, 0.18, 0.03]} pos={[-0.08, h * 0.5, d / 2 + 0.02]} color="#cbd5e1" rough={0.3} />
          <Slab size={[0.03, 0.18, 0.03]} pos={[0.08, h * 0.5, d / 2 + 0.02]} color="#cbd5e1" rough={0.3} />
        </group>
      );
    case "safe":
      return (
        <group>
          {body}
          <Slab size={[w * 0.78, h * 0.78, 0.02]} pos={[0, h * 0.5, d / 2 + 0.01]} color={dark} rough={0.35} />
          <mesh position={[w * 0.12, h * 0.52, d / 2 + 0.03]} rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[Math.min(w, h) * 0.12, Math.min(w, h) * 0.12, 0.03, 20]} /><meshStandardMaterial color="#e2e8f0" metalness={0.8} roughness={0.25} /></mesh>
          <Slab size={[0.04, h * 0.22, 0.03]} pos={[-w * 0.22, h * 0.5, d / 2 + 0.035]} color="#cbd5e1" rough={0.3} />
        </group>
      );
    case "desk":
      return (
        <group>
          <Slab size={[w, 0.05, d]} pos={[0, h - 0.025, 0]} color={light} rough={0.45} />
          <Slab size={[w * 0.28, h - 0.05, d * 0.9]} pos={[-w / 2 + w * 0.14 + 0.02, (h - 0.05) / 2, 0]} color={c} />
          {[0.22, 0.5, 0.78].map((f, i) => (
            <Slab key={i} size={[w * 0.2, 0.025, 0.02]} pos={[-w / 2 + w * 0.14 + 0.02, (h - 0.05) * f, d * 0.45 + 0.012]} color="#cbd5e1" rough={0.3} />
          ))}
          <Slab size={[0.05, h - 0.05, 0.05]} pos={[w / 2 - 0.05, (h - 0.05) / 2, -d / 2 + 0.05]} color={dark} />
          <Slab size={[0.05, h - 0.05, 0.05]} pos={[w / 2 - 0.05, (h - 0.05) / 2, d / 2 - 0.05]} color={dark} />
          <mesh position={[0, h / 2, 0]}><boxGeometry args={[w, h, d]} /><meshBasicMaterial visible={false} /><Edges color={edge} /></mesh>
        </group>
      );
    case "table":
      return (
        <group>
          <Slab size={[w, 0.05, d]} pos={[0, h - 0.025, 0]} color={light} rough={0.45} />
          {[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([sx, sz], i) => (
            <Slab key={i} size={[0.06, h - 0.05, 0.06]} pos={[(sx * (w - 0.1)) / 2, (h - 0.05) / 2, (sz * (d - 0.1)) / 2]} color={dark} />
          ))}
          <mesh position={[0, h / 2, 0]}><boxGeometry args={[w, h, d]} /><meshBasicMaterial visible={false} /><Edges color={edge} /></mesh>
        </group>
      );
    case "chair":
      return (
        <group>
          <Slab size={[w, 0.06, d]} pos={[0, h * 0.5, 0]} color={c} />
          <Slab size={[w, h * 0.5, 0.05]} pos={[0, h * 0.75, -d / 2 + 0.025]} color={dark} />
          {[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([sx, sz], i) => (
            <Slab key={i} size={[0.05, h * 0.5, 0.05]} pos={[(sx * (w - 0.08)) / 2, h * 0.25, (sz * (d - 0.08)) / 2]} color={dark} />
          ))}
          <mesh position={[0, h / 2, 0]}><boxGeometry args={[w, h, d]} /><meshBasicMaterial visible={false} /><Edges color={edge} /></mesh>
        </group>
      );
    case "bed":
      return (
        <group>
          <Slab size={[w, h * 0.45, d]} pos={[0, h * 0.225, 0]} color={dark} />
          <Slab size={[w - 0.1, h * 0.35, d - 0.1]} pos={[0, h * 0.62, 0]} color={light} rough={0.9} />
          <Slab size={[w * 0.7, 0.1, 0.35]} pos={[0, h * 0.85, -d / 2 + 0.3]} color="#f1f5f9" rough={0.95} />
          <mesh position={[0, h / 2, 0]}><boxGeometry args={[w, h, d]} /><meshBasicMaterial visible={false} /><Edges color={edge} /></mesh>
        </group>
      );
    case "appliance":
      return (
        <group>
          {body}
          <Slab size={[w * 0.6, h * 0.12, 0.02]} pos={[0, h * 0.82, d / 2 + 0.01]} color="#0f172a" rough={0.3} />
          <mesh position={[w * 0.28, h * 0.62, d / 2 + 0.02]}><cylinderGeometry args={[0.03, 0.03, 0.03, 12]} /><meshStandardMaterial color="#e2e8f0" /></mesh>
        </group>
      );
    case "vehicle": {
      const r = Math.min(0.34, h * 0.28);
      const lengthAlongZ = d >= w;
      const L = Math.max(w, d);
      const W = Math.min(w, d);
      return (
        <group rotation={[0, lengthAlongZ ? 0 : Math.PI / 2, 0]}>
          <Slab size={[W, h * 0.42, L]} pos={[0, r + h * 0.21, 0]} color={c} rough={0.35} />
          <Slab size={[W * 0.92, h * 0.38, L * 0.5]} pos={[0, r + h * 0.42 + h * 0.19, -L * 0.04]} color={shade(c, 0.85)} rough={0.25} />
          <Slab size={[W * 0.94, h * 0.2, L * 0.46]} pos={[0, r + h * 0.45 + h * 0.19, -L * 0.04]} color="#0b1220" rough={0.1} />
          {[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([sx, sz], i) => (
            <mesh key={i} position={[(sx * W) / 2, r, (sz * L * 0.32)]} rotation={[0, 0, Math.PI / 2]} castShadow>
              <cylinderGeometry args={[r, r, 0.22, 16]} />
              <meshStandardMaterial color="#111827" roughness={0.9} />
            </mesh>
          ))}
          <mesh position={[0, h / 2, 0]}><boxGeometry args={[W, h, L]} /><meshBasicMaterial visible={false} /><Edges color={edge} /></mesh>
        </group>
      );
    }
    case "tree":
      return (
        <group>
          <mesh position={[0, h * 0.25, 0]} castShadow><cylinderGeometry args={[Math.min(w, d) * 0.08, Math.min(w, d) * 0.12, h * 0.5, 8]} /><meshStandardMaterial color="#6b4423" /></mesh>
          <mesh position={[0, h * 0.7, 0]} castShadow><sphereGeometry args={[Math.max(w, d) * 0.45, 12, 10]} /><meshStandardMaterial color="#2f6b3a" roughness={0.9} /></mesh>
        </group>
      );
    case "fence":
      return (
        <group>
          <Slab size={[w, h, Math.min(d, 0.12)]} pos={[0, h / 2, 0]} color={dark} />
          <Slab size={[w, 0.06, Math.min(d, 0.14)]} pos={[0, h, 0]} color={c} />
        </group>
      );
    default:
      return body;
  }
}
