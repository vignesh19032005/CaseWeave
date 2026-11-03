"use client";

// Real 3D models for a few common categories, with the plain parametric shape as the fallback. A model is only used when
// - the object is not an assumed one (assumed objects stay visibly schematic, with their red outline),
// - its label matches what the model actually is, and
// - the real footprint has roughly the same proportions as the model, so nothing is stretched out of shape.
// If the file is missing, slow or fails to load, the scene shows the parametric shape instead. Licences: public/models/LICENSES.md.
import React, { Component, Suspense, useMemo } from "react";
import * as THREE from "three";
import { useGLTF } from "@react-three/drei";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";
import type { FurnitureKind } from "./SandboxFurniture";

export interface ModelSpec { url: string; kinds: FurnitureKind[]; label: RegExp; notLabel?: RegExp; name: string; credit: string }

export const MODEL_SPECS: ModelSpec[] = [
  { url: "/models/ChairDamaskPurplegold.glb", kinds: ["chair"], label: /chair|armchair/i, notLabel: /sofa|couch|stool|bench/i, name: "Damask chair", credit: "Wayfair, CC BY 4.0 (Khronos glTF Sample Assets)" },
  { url: "/models/CesiumMilkTruck.glb", kinds: ["vehicle"], label: /truck|lorry|van\b/i, name: "Delivery truck", credit: "Cesium, CC BY 4.0 (Khronos glTF Sample Assets)" },
];
export const PERSON_MODEL = { url: "/models/CesiumMan.glb", name: "Walking figure", credit: "Cesium, CC BY 4.0 (Khronos glTF Sample Assets)" };

export function modelFor(kind: FurnitureKind, label: string): ModelSpec | null {
  return MODEL_SPECS.find((m) => m.kinds.includes(kind) && m.label.test(label) && !(m.notLabel && m.notLabel.test(label))) ?? null;
}

/** Falls back to its `fallback` if anything below it throws (file missing, bad GLB). The scene never breaks because of a model. */
export class ModelBoundary extends Component<{ fallback: React.ReactNode; children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { /* the fallback is already shown */ }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

const scratch = new THREE.Box3();
const sizeV = new THREE.Vector3();
const centreV = new THREE.Vector3();

/** A uniform scale and offset that sit the model on the floor, centred in the footprint, as large as fits. */
export function fitModel(root: THREE.Object3D, w: number, d: number, h: number, turned = false): { scale: number; offset: [number, number, number]; ratio: number } {
  scratch.setFromObject(root);
  scratch.getSize(sizeV);
  scratch.getCenter(centreV);
  const fw = turned ? d : w, fd = turned ? w : d;      // turned a quarter turn: the model's long side lies along the footprint's other side
  const s = Math.min(fw / Math.max(sizeV.x, 1e-6), fd / Math.max(sizeV.z, 1e-6), h / Math.max(sizeV.y, 1e-6));
  // how far the model's proportions are from the real footprint: 1 means a perfect fit on both sides
  const ratio = Math.min((sizeV.x * s) / fw, (sizeV.z * s) / fd);
  return { scale: s, offset: [-centreV.x * s, -scratch.min.y * s, -centreV.z * s], ratio };
}

function LoadedModel({ spec, w, d, h, fallback }: { spec: ModelSpec; w: number; d: number; h: number; fallback: React.ReactNode }) {
  const gltf = useGLTF(spec.url);
  const fit = useMemo(() => {
    const root = gltf.scene.clone(true);
    root.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; }
    });
    const straight = fitModel(root, w, d, h), turned = fitModel(root, w, d, h, true);
    return turned.ratio > straight.ratio + 0.05 ? { root, ...turned, turned: true } : { root, ...straight, turned: false };
  }, [gltf, w, d, h]);
  if (fit.ratio < 0.65) return <>{fallback}</>;     // would be a very different shape from the real footprint: keep the plain box
  return (
    <group rotation={[0, fit.turned ? Math.PI / 2 : 0, 0]}>
      <group position={fit.offset} scale={fit.scale}>
        <primitive object={fit.root} />
      </group>
    </group>
  );
}

/** The model for this object when one fits, otherwise the parametric shape passed as `fallback`. */
export function ModelOrFallback({ spec, w, d, h, fallback }: { spec: ModelSpec; w: number; d: number; h: number; fallback: React.ReactNode }) {
  return (
    <ModelBoundary fallback={fallback}>
      <Suspense fallback={fallback}>
        <LoadedModel spec={spec} w={w} d={d} h={h} fallback={fallback} />
      </Suspense>
    </ModelBoundary>
  );
}

/** Size from the skinned vertices as they really are posed (precise bounds), not the mesh's rest bounds, which can be several times off. Feet on the floor, centred. */
/** Applies the first frame of the clip, so the size is measured the way the figure will really be drawn (the clip can rescale the skeleton). */
export function poseAtStart(root: THREE.Object3D, clip?: THREE.AnimationClip) {
  if (!clip) return;
  const m = new THREE.AnimationMixer(root);
  m.clipAction(clip).play();
  m.update(0);
  root.updateMatrixWorld(true);
}

export function fitRigged(root: THREE.Object3D, height: number): { scale: number; offset: [number, number, number] } {
  root.updateMatrixWorld(true);
  scratch.makeEmpty();
  scratch.setFromObject(root, true);
  scratch.getSize(sizeV);
  scratch.getCenter(centreV);
  if (sizeV.y < 1e-6) return { scale: 1, offset: [0, 0, 0] };
  const s = height / sizeV.y;
  return { scale: s, offset: [-centreV.x * s, -scratch.min.y * s, -centreV.z * s] };
}

/** A private copy of a rigged model (own skeleton and materials) so several people can share one download. */
export function useRiggedClone(url: string, height: number) {
  const gltf = useGLTF(url);
  return useMemo(() => {
    const root = cloneSkinned(gltf.scene);
    root.traverse((o) => {
      const m = o as THREE.Mesh;
      if (m.isMesh) {
        m.castShadow = true;
        m.frustumCulled = false;     // skinned meshes move outside their rest bounding box
        const mat = m.material;
        m.material = Array.isArray(mat) ? mat.map((x) => x.clone()) : mat.clone();
      }
    });
    poseAtStart(root, gltf.animations[0]);
    const f = fitRigged(root, height);
    return { root, scale: f.scale, offset: f.offset, clips: gltf.animations };
  }, [gltf, height]);
}

export function preloadModels() {
  for (const m of MODEL_SPECS) useGLTF.preload(m.url);
  useGLTF.preload(PERSON_MODEL.url);
}

/** Starts a clip and holds it, so the caller can set its time directly (feet follow distance travelled, not the clock). */
export function holdClip(action: THREE.AnimationAction | null) {
  if (!action) return;
  action.play();
  action.paused = true;
}

/** Jumps a held clip to `time` seconds and applies it to the skeleton. */
export function seekClip(action: THREE.AnimationAction | null, mixer: THREE.AnimationMixer, time: number) {
  if (!action) return;
  action.time = time;
  mixer.update(0);
}

/** Tints the figure's (mostly white) clothing with the person's colour, so each person can be told apart. */
export function tintFigure(root: THREE.Object3D, color: string) {
  const c = new THREE.Color(color).lerp(new THREE.Color("#ffffff"), 0.3);
  root.traverse((o) => {
    const m = (o as THREE.Mesh).material as THREE.MeshStandardMaterial | THREE.MeshStandardMaterial[] | undefined;
    for (const mat of Array.isArray(m) ? m : m ? [m] : []) if (mat.color) mat.color.copy(c);
  });
}
