"use client";

// A stylised "point view": every solid surface in the model is redrawn as a cloud of small dots, for a look reminiscent of a scan.
// It is NOT scan data and not a measurement. The dots are sampled from the same model the scene already draws (which comes from the evidence
// and from labelled assumptions), so it shows nothing the normal view does not. It only changes how the scene looks.
import { useEffect } from "react";
import * as THREE from "three";
import { useThree } from "@react-three/fiber";
import { MeshSurfaceSampler } from "three/examples/jsm/math/MeshSurfaceSampler.js";

const MAX_PER_MESH = 5000;
const MAX_TOTAL = 160000;
const DOTS_PER_M2 = 90;

const tmpPos = new THREE.Vector3();
const tmpCol = new THREE.Color();
const bbox = new THREE.Box3();
const size = new THREE.Vector3();

function solid(m: THREE.Mesh): THREE.MeshStandardMaterial | null {
  const mat = Array.isArray(m.material) ? m.material[0] : m.material;
  if (!mat || (mat as THREE.Material).transparent && (mat as THREE.Material).opacity < 0.9) return null;   // glass-like volumes (view cones) stay as they are
  return mat as THREE.MeshStandardMaterial;
}

function dotsFor(mesh: THREE.Mesh, budget: number): THREE.Points | null {
  const mat = solid(mesh);
  if (!mat || !mesh.geometry || (mesh as THREE.SkinnedMesh).isSkinnedMesh || (mesh as THREE.Mesh & { isInstancedMesh?: boolean }).isInstancedMesh) return null;
  const pos = mesh.geometry.getAttribute("position");
  if (!pos || pos.count < 3 || (mat as unknown as { wireframe?: boolean }).wireframe) return null;
  mesh.geometry.computeBoundingBox();
  bbox.copy(mesh.geometry.boundingBox as THREE.Box3).getSize(size);
  const s = mesh.scale;
  const area = 2 * (size.x * s.x * size.y * s.y + size.y * s.y * size.z * s.z + size.x * s.x * size.z * s.z);
  const n = Math.min(MAX_PER_MESH, budget, Math.max(30, Math.round(area * DOTS_PER_M2)));
  if (n <= 0) return null;
  const sampler = new MeshSurfaceSampler(mesh).build();
  const p = new Float32Array(n * 3), c = new Float32Array(n * 3);
  const base = (mat as THREE.MeshStandardMaterial).color ?? tmpCol.set("#9ca3af");
  for (let i = 0; i < n; i++) {
    sampler.sample(tmpPos);
    p.set([tmpPos.x, tmpPos.y, tmpPos.z], i * 3);
    const j = 0.8 + Math.random() * 0.35;
    c.set([Math.min(1, base.r * j + 0.08), Math.min(1, base.g * j + 0.08), Math.min(1, base.b * j + 0.08)], i * 3);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(p, 3));
  g.setAttribute("color", new THREE.BufferAttribute(c, 3));
  const pts = new THREE.Points(g, new THREE.PointsMaterial({ size: 0.035, vertexColors: true, sizeAttenuation: true }));
  pts.position.copy(mesh.position); pts.quaternion.copy(mesh.quaternion); pts.scale.copy(mesh.scale);
  pts.userData.pointView = true;
  return pts;
}

function build(scene: THREE.Scene, made: THREE.Points[], hidden: THREE.Mesh[], budget: { left: number }) {
  const todo: THREE.Mesh[] = [];
  scene.traverse((o) => {
    const m = o as THREE.Mesh;
    if (m.isMesh && !m.userData.pvDone && !m.userData.pointView && m.parent) todo.push(m);
  });
  for (const m of todo) {
    m.userData.pvDone = true;
    if (budget.left <= 0) break;
    const pts = dotsFor(m, budget.left);
    if (!pts) continue;
    m.parent!.add(pts);
    budget.left -= pts.geometry.getAttribute("position").count;
    m.visible = false;
    made.push(pts); hidden.push(m);
  }
}

/** Switches the scene to dots while `enabled`, and puts everything back exactly as it was when switched off. */
export default function PointView({ enabled }: { enabled: boolean }) {
  const scene = useThree((s) => s.scene);
  useEffect(() => {
    if (!enabled) return;
    const made: THREE.Points[] = [], hidden: THREE.Mesh[] = [], budget = { left: MAX_TOTAL };
    build(scene, made, hidden, budget);
    const timer = window.setInterval(() => build(scene, made, hidden, budget), 1500);   // catches models that finish loading later
    return () => {
      window.clearInterval(timer);
      for (const p of made) { p.parent?.remove(p); p.geometry.dispose(); (p.material as THREE.Material).dispose(); }
      for (const m of hidden) { m.visible = true; delete m.userData.pvDone; }
      scene.traverse((o) => { if (o.userData.pvDone) delete o.userData.pvDone; });
    };
  }, [enabled, scene]);
  return null;
}
