/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import React, { useRef, useEffect } from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";

export interface SimulationFrame {
  frame_idx: number;
  timestamp: string;
  time_seconds: number;
  phase: string;
  title: string;
  narrative: string;
  actor: {
    visible: boolean;
    pos: [number, number, number];
    action: string;
    label: string;
  };
  scene_state: {
    shutter_height: number;
    shutter_color: string;
    shutter_alert: boolean;
    vault_toppled: boolean;
    counter_open: boolean;
    active_sensor: string;
    sensor_color: string;
  };
  evidence_markers: Array<{
    marker_id: string;
    label: string;
    pos: [number, number, number];
    color: string;
    filename?: string;
  }>;
  conflict_alert?: {
    title: string;
    source_a: string;
    source_b: string;
    nature: string;
    admissibility_rule: string;
  } | null;
  telemetry: {
    sensor_event: string;
    cctv_frame: string;
    witness_statement: string;
    evidence_doc: string;
  };
  camera_preset: string;
}

export interface SimulationData {
  case_id: string;
  title: string;
  scene_config: {
    width_m: number;
    length_m: number;
    height_m: number;
    zones: Record<string, { center: [number, number, number]; label: string; color: string }>;
    camera_presets: Record<string, { pos: [number, number, number]; target: [number, number, number]; label: string }>;
  };
  trajectory: Array<{ time: string; pos: [number, number, number]; action: string; label: string }>;
  frames: SimulationFrame[];
  total_duration_sec: number;
  total_frames: number;
}

interface CameraControllerProps {
  preset: string;
  presets: Record<string, { pos: [number, number, number]; target: [number, number, number] }>;
}

function CameraController({ preset, presets }: CameraControllerProps) {
  const { camera } = useThree();
  const controlsRef = useRef<any>(null);
  const targetPos = useRef(new THREE.Vector3(11, 11, 11));
  const targetLook = useRef(new THREE.Vector3(0, 1, 0));

  useEffect(() => {
    const config = presets[preset] || presets["overview"];
    if (config) {
      targetPos.current.set(...config.pos);
      targetLook.current.set(...config.target);
    }
  }, [preset, presets]);

  useFrame(() => {
    // Smooth lerp to camera preset position
    camera.position.lerp(targetPos.current, 0.05);
    if (controlsRef.current) {
      controlsRef.current.target.lerp(targetLook.current, 0.05);
      controlsRef.current.update();
    }
  });

  return <OrbitControls ref={controlsRef} makeDefault maxPolarAngle={Math.PI / 2.05} minDistance={2} maxDistance={30} />;
}

/**
 * 3D Forensic Scene Environment
 */
function ForensicScene({
  frame,
  trajectory,
  zones,
}: {
  frame: SimulationFrame;
  trajectory: Array<{ pos: [number, number, number] }>;
  zones: Record<string, { center: [number, number, number]; label: string; color: string }>;
}) {
  const actorRef = useRef<THREE.Group>(null);
  const currentActorPos = useRef(new THREE.Vector3(-4.5, 0, -9));

  // Trajectory points for path line
  const linePoints = React.useMemo(() => {
    return trajectory.map((t) => new THREE.Vector3(t.pos[0], 0.08, t.pos[2]));
  }, [trajectory]);

  // Smooth actor position update
  useFrame(() => {
    if (frame?.actor && actorRef.current) {
      const target = new THREE.Vector3(...frame.actor.pos);
      currentActorPos.current.lerp(target, 0.08);
      actorRef.current.position.copy(currentActorPos.current);
    }
  });

  const shutterHeight = frame?.scene_state?.shutter_height ?? 0;
  const isVaultToppled = frame?.scene_state?.vault_toppled ?? false;
  const isCounterOpen = frame?.scene_state?.counter_open ?? false;
  const isShutterAlert = frame?.scene_state?.shutter_alert ?? false;

  return (
    <group>
      {/* Lighting */}
      <ambientLight intensity={0.55} />
      <directionalLight position={[10, 18, 8]} intensity={0.9} castShadow />
      <pointLight position={[-4.5, 3.5, -5.5]} intensity={isShutterAlert ? 2.5 : 0.8} color={isShutterAlert ? "#ef4444" : "#ffffff"} />
      <pointLight position={[3.8, 3.2, -2.5]} intensity={isVaultToppled ? 2.0 : 0.7} color={isVaultToppled ? "#f59e0b" : "#38bdf8"} />

      {/* Grid Floor */}
      <gridHelper args={[24, 24, "#3f3f46", "#18181b"]} position={[0, 0, 0]} />

      {/* Crime Scene Floor Boundary */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]}>
        <planeGeometry args={[14, 18]} />
        <meshStandardMaterial color="#090a0f" roughness={0.9} metalness={0.1} />
      </mesh>

      {/* Outer Walls (Tactical Perimeter Wireframe / Low Walls) */}
      {/* Rear Alley Wall */}
      <mesh position={[0, 1.5, -7.0]}>
        <boxGeometry args={[14, 3, 0.3]} />
        <meshStandardMaterial color="#27272a" transparent opacity={0.8} />
      </mesh>
      {/* Front Entrance Wall */}
      <mesh position={[0, 1.5, 7.0]}>
        <boxGeometry args={[14, 3, 0.3]} />
        <meshStandardMaterial color="#27272a" transparent opacity={0.4} />
      </mesh>
      {/* Left Wall */}
      <mesh position={[-7.0, 1.5, 0]}>
        <boxGeometry args={[0.3, 3, 14]} />
        <meshStandardMaterial color="#27272a" transparent opacity={0.5} />
      </mesh>
      {/* Right Wall */}
      <mesh position={[7.0, 1.5, 0]}>
        <boxGeometry args={[0.3, 3, 14]} />
        <meshStandardMaterial color="#27272a" transparent opacity={0.5} />
      </mesh>

      {/* -------------------- REAR ROLLING SHUTTER (Gate-B) -------------------- */}
      <group position={[-4.5, 0, -6.85]}>
        {/* Shutter Door Frame */}
        <mesh position={[-1.6, 1.6, 0]}>
          <boxGeometry args={[0.25, 3.2, 0.3]} />
          <meshStandardMaterial color="#52525b" />
        </mesh>
        <mesh position={[1.6, 1.6, 0]}>
          <boxGeometry args={[0.25, 3.2, 0.3]} />
          <meshStandardMaterial color="#52525b" />
        </mesh>
        <mesh position={[0, 3.2, 0]}>
          <boxGeometry args={[3.45, 0.3, 0.3]} />
          <meshStandardMaterial color="#52525b" />
        </mesh>

        {/* Dynamic Rolling Shutter Slats (Moves Upward as shutterHeight increases) */}
        <mesh position={[0, 1.6 + shutterHeight / 2, 0]}>
          <boxGeometry args={[3.0, Math.max(0.1, 3.0 - shutterHeight), 0.1]} />
          <meshStandardMaterial
            color={isShutterAlert ? "#ef4444" : "#71717a"}
            metalness={0.7}
            roughness={0.3}
          />
        </mesh>

        {/* Shutter Tamper Sensor Beacon Light */}
        <mesh position={[0, 3.45, 0.15]}>
          <sphereGeometry args={[0.12, 16, 16]} />
          <meshStandardMaterial
            color={isShutterAlert ? "#ef4444" : "#10b981"}
            emissive={isShutterAlert ? "#ef4444" : "#10b981"}
            emissiveIntensity={isShutterAlert ? 2.5 : 0.8}
          />
        </mesh>
      </group>

      {/* -------------------- CCTV-ALLEY-02 Camera -------------------- */}
      <group position={[-6.2, 3.2, -6.85]} rotation={[0.4, 0.6, 0]}>
        <mesh>
          <boxGeometry args={[0.3, 0.3, 0.7]} />
          <meshStandardMaterial color="#fafafa" metalness={0.8} />
        </mesh>
        {/* Camera Lens */}
        <mesh position={[0, 0, 0.4]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.1, 0.1, 0.15, 16]} />
          <meshStandardMaterial color="#0284c7" emissive="#0284c7" emissiveIntensity={0.8} />
        </mesh>
      </group>

      {/* -------------------- STORAGE CORRIDOR & RACKS -------------------- */}
      <group position={[-2.0, 0, -2.0]}>
        {/* Industrial Shelf 1 */}
        <mesh position={[-0.8, 1.5, 0]}>
          <boxGeometry args={[0.6, 3.0, 3.5]} />
          <meshStandardMaterial color="#334155" wireframe />
        </mesh>
        {/* Storage Boxes on Shelf */}
        <mesh position={[-0.8, 0.6, -0.8]}>
          <boxGeometry args={[0.5, 0.5, 0.7]} />
          <meshStandardMaterial color="#d97706" />
        </mesh>
        <mesh position={[-0.8, 1.4, 0.5]}>
          <boxGeometry args={[0.5, 0.5, 0.8]} />
          <meshStandardMaterial color="#b45309" />
        </mesh>
        {/* PIR Ceiling Motion Sensor */}
        <mesh position={[0, 3.8, 0]}>
          <cylinderGeometry args={[0.2, 0.25, 0.1, 16]} />
          <meshStandardMaterial
            color={frame?.scene_state?.active_sensor?.includes("PIR") ? "#f59e0b" : "#64748b"}
            emissive={frame?.scene_state?.active_sensor?.includes("PIR") ? "#f59e0b" : "#000000"}
          />
        </mesh>
      </group>

      {/* -------------------- NARCOTICS VAULT -------------------- */}
      <group position={[3.8, 0, -2.5]}>
        {/* Vault Boundary Cage / Wall */}
        <mesh position={[0, 1.5, -1.8]}>
          <boxGeometry args={[3.2, 3.0, 0.1]} />
          <meshStandardMaterial color="#1e293b" transparent opacity={0.6} />
        </mesh>
        <mesh position={[-1.6, 1.5, 0]}>
          <boxGeometry args={[0.1, 3.0, 3.6]} />
          <meshStandardMaterial color="#1e293b" transparent opacity={0.6} />
        </mesh>

        {/* High-Value Medicine Cabinet (Tilts/Topples when Looted!) */}
        <group
          position={[0.2, isVaultToppled ? 0.35 : 1.1, 0]}
          rotation={isVaultToppled ? [0, 0, Math.PI / 2.3] : [0, 0, 0]}
        >
          <mesh>
            <boxGeometry args={[0.9, 2.2, 1.4]} />
            <meshStandardMaterial
              color={isVaultToppled ? "#f59e0b" : "#e2e8f0"}
              metalness={0.6}
              roughness={0.2}
            />
          </mesh>
          {/* Glass Doors / Shelves */}
          <mesh position={[0.46, 0, 0]}>
            <boxGeometry args={[0.02, 2.0, 1.2]} />
            <meshStandardMaterial color="#38bdf8" transparent opacity={0.4} />
          </mesh>
        </group>
      </group>

      {/* -------------------- FRONT BILLING COUNTER & CASH TILL -------------------- */}
      <group position={[2.2, 0, 3.8]}>
        {/* Wooden Counter Desk */}
        <mesh position={[0, 0.55, 0]}>
          <boxGeometry args={[3.0, 1.1, 1.2]} />
          <meshStandardMaterial color="#78350f" roughness={0.7} />
        </mesh>
        {/* Computer Screen / POS */}
        <mesh position={[-0.8, 1.3, 0]}>
          <boxGeometry args={[0.1, 0.4, 0.6]} />
          <meshStandardMaterial color="#1e293b" />
        </mesh>
        {/* Cash Till Drawer (Slides Forward when Ransacked) */}
        <mesh position={[0.6, 0.9, isCounterOpen ? 0.8 : 0.45]}>
          <boxGeometry args={[0.8, 0.25, 0.6]} />
          <meshStandardMaterial
            color={isCounterOpen ? "#ef4444" : "#475569"}
            metalness={0.5}
          />
        </mesh>
      </group>

      {/* -------------------- TRAJECTORY LINE OVERLAY -------------------- */}
      {linePoints.length > 1 && (
        <primitive
          object={
            new THREE.Line(
              new THREE.BufferGeometry().setFromPoints(linePoints),
              new THREE.LineDashedMaterial({
                color: 0x06b6d4,
                linewidth: 2,
                dashSize: 0.4,
                gapSize: 0.2,
              })
            )
          }
        />
      )}

      {/* Waypoint Floor Markers */}
      {trajectory.map((w, i) => (
        <mesh key={i} position={[w.pos[0], 0.04, w.pos[2]]} rotation={[-Math.PI / 2, 0, 0]}>
          <circleGeometry args={[0.25, 16]} />
          <meshBasicMaterial color="#06b6d4" transparent opacity={0.3} />
        </mesh>
      ))}

      {/* -------------------- EVIDENCE MARKERS ON SCENE -------------------- */}
      {frame?.evidence_markers?.map((em, idx) => (
        <group key={idx} position={[em.pos[0], em.pos[1], em.pos[2]]}>
          {/* Yellow Forensic A-Frame Tent */}
          <mesh position={[0, 0.15, 0]} rotation={[0, Math.PI / 4, 0]}>
            <coneGeometry args={[0.18, 0.3, 4]} />
            <meshStandardMaterial color="#facc15" roughness={0.3} />
          </mesh>
          {/* Ground Marker Ring */}
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
            <ringGeometry args={[0.25, 0.35, 16]} />
            <meshBasicMaterial color={em.color || "#facc15"} />
          </mesh>
        </group>
      ))}

      {/* -------------------- 3D SUSPECT AVATAR -------------------- */}
      {frame?.actor?.visible && (
        <group ref={actorRef} position={frame.actor.pos}>
          {/* Pulsing Floor Target Indicator */}
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>
            <ringGeometry args={[0.4, 0.5, 32]} />
            <meshBasicMaterial color="#ef4444" transparent opacity={0.8} />
          </mesh>

          {/* Torso / Dark Hooded Rain Jacket */}
          <mesh position={[0, 1.1, 0]}>
            <capsuleGeometry args={[0.26, 0.75, 8, 16]} />
            <meshStandardMaterial color="#18181b" roughness={0.4} />
          </mesh>

          {/* Head / Hood */}
          <mesh position={[0, 1.7, 0]}>
            <sphereGeometry args={[0.22, 16, 16]} />
            <meshStandardMaterial color="#27272a" roughness={0.5} />
          </mesh>

          {/* Legs */}
          <mesh position={[-0.12, 0.45, 0]}>
            <cylinderGeometry args={[0.08, 0.08, 0.7, 8]} />
            <meshStandardMaterial color="#18181b" />
          </mesh>
          <mesh position={[0.12, 0.45, 0]}>
            <cylinderGeometry args={[0.08, 0.08, 0.7, 8]} />
            <meshStandardMaterial color="#18181b" />
          </mesh>

          {/* White Sports Shoes (From Witness / CCTV Observation) */}
          <mesh position={[-0.12, 0.08, 0.08]}>
            <boxGeometry args={[0.12, 0.1, 0.24]} />
            <meshStandardMaterial color="#f8fafc" />
          </mesh>
          <mesh position={[0.12, 0.08, 0.08]}>
            <boxGeometry args={[0.12, 0.1, 0.24]} />
            <meshStandardMaterial color="#f8fafc" />
          </mesh>
        </group>
      )}
    </group>
  );
}

export default function SimulationPlayer({
  simulation,
  currentFrameIdx,
  setCurrentFrameIdx,
  isPlaying,
  setIsPlaying,
  playbackSpeed,
  setPlaybackSpeed,
  cameraPreset,
  setCameraPreset,
}: {
  simulation: SimulationData;
  currentFrameIdx: number;
  setCurrentFrameIdx: React.Dispatch<React.SetStateAction<number>>;
  isPlaying: boolean;
  setIsPlaying: React.Dispatch<React.SetStateAction<boolean>>;
  playbackSpeed: number;
  setPlaybackSpeed: (speed: number) => void;
  cameraPreset: string;
  setCameraPreset: (preset: string) => void;
}) {
  const frames = simulation?.frames || [];
  const currentFrame = frames[currentFrameIdx] || frames[0];
  const presets = simulation?.scene_config?.camera_presets || {
    overview: { pos: [11, 11, 11], target: [0, 1, 0], label: "Overview 360°" },
  };

  // Playback timer effect
  useEffect(() => {
    if (!isPlaying) return;
    const intervalMs = Math.round(3000 / playbackSpeed);
    const timer = setInterval(() => {
      setCurrentFrameIdx((prev) => {
        if (prev >= frames.length - 1) {
          setIsPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, intervalMs);
    return () => clearInterval(timer);
  }, [isPlaying, playbackSpeed, frames.length, setCurrentFrameIdx, setIsPlaying]);

  if (!simulation || frames.length === 0) {
    return (
      <div className="h-96 flex items-center justify-center text-xs text-zinc-500 border border-dashed border-zinc-800 rounded">
        No simulation data available.
      </div>
    );
  }

  return (
    <div className="flex flex-col border border-zinc-800 rounded-xl bg-zinc-950 overflow-hidden shadow-2xl">
      {/* ----------------- TOP PLAYBACK HUD CONTROLLER ----------------- */}
      <div className="px-4 py-3 bg-zinc-900/90 border-b border-zinc-800/80 flex flex-wrap items-center justify-between gap-3">
        {/* Time & Phase Badge */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-zinc-950 border border-zinc-800">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-xs font-mono font-bold text-emerald-400 tracking-wider">
              {currentFrame.timestamp}
            </span>
          </div>
          <span className="text-[11px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded bg-indigo-950/80 border border-indigo-700/60 text-indigo-300">
            {currentFrame.phase}
          </span>
          <span className="text-xs text-zinc-300 font-medium hidden sm:inline truncate max-w-xs">
            {currentFrame.title}
          </span>
        </div>

        {/* Transport Controls */}
        <div className="flex items-center gap-1.5">
          {/* Step to Start */}
          <button
            onClick={() => {
              setIsPlaying(false);
              setCurrentFrameIdx(0);
            }}
            title="Jump to Start"
            className="p-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs transition"
          >
            ⏮
          </button>
          {/* Prev Step */}
          <button
            onClick={() => {
              setIsPlaying(false);
              setCurrentFrameIdx((p) => Math.max(0, p - 1));
            }}
            title="Previous Event"
            className="p-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs transition"
          >
            ◀
          </button>
          {/* Play / Pause */}
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className={`px-3 py-1.5 rounded font-bold text-xs flex items-center gap-1.5 transition ${
              isPlaying
                ? "bg-amber-600 hover:bg-amber-500 text-white"
                : "bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/40"
            }`}
          >
            {isPlaying ? "⏸ PAUSE" : "▶ PLAY"}
          </button>
          {/* Next Step */}
          <button
            onClick={() => {
              setIsPlaying(false);
              setCurrentFrameIdx((p) => Math.min(frames.length - 1, p + 1));
            }}
            title="Next Event"
            className="p-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs transition"
          >
            ▶
          </button>
          {/* Step to End */}
          <button
            onClick={() => {
              setIsPlaying(false);
              setCurrentFrameIdx(frames.length - 1);
            }}
            title="Jump to End"
            className="p-1.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs transition"
          >
            ⏭
          </button>

          {/* Speed Selector */}
          <div className="ml-2 flex items-center border border-zinc-800 rounded bg-zinc-950 p-0.5 text-[10px]">
            {[0.5, 1, 2, 5].map((spd) => (
              <button
                key={spd}
                onClick={() => setPlaybackSpeed(spd)}
                className={`px-1.5 py-0.5 rounded ${
                  playbackSpeed === spd ? "bg-indigo-600 text-white font-bold" : "text-zinc-400 hover:text-white"
                }`}
              >
                {spd}x
              </button>
            ))}
          </div>
        </div>

        {/* Camera Angle Presets */}
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-zinc-500 uppercase mr-1 hidden md:inline">Camera:</span>
          {Object.entries(presets).map(([k, v]) => (
            <button
              key={k}
              onClick={() => setCameraPreset(k)}
              className={`px-2 py-1 rounded text-[10px] transition ${
                cameraPreset === k
                  ? "bg-indigo-600 text-white font-medium shadow"
                  : "bg-zinc-800 text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {k === "overview"
                ? "🌐 360°"
                : k === "cctv_alley"
                ? "📹 CCTV-2"
                : k === "vault_cam"
                ? "🔒 Vault"
                : k === "counter_cam"
                ? "💵 Till"
                : "🚶 POV"}
            </button>
          ))}
        </div>
      </div>

      {/* ----------------- CHRONOLOGICAL TIMELINE SCRUBBER ----------------- */}
      <div className="px-4 py-2 bg-zinc-950 border-b border-zinc-800/60">
        <div className="flex items-center justify-between text-[10px] text-zinc-400 mb-1">
          <span>{frames[0]?.timestamp}</span>
          <span className="text-zinc-500">Timeline Scrubber (Step {currentFrameIdx + 1} of {frames.length})</span>
          <span>{frames[frames.length - 1]?.timestamp}</span>
        </div>
        <div className="relative flex items-center">
          <input
            type="range"
            min={0}
            max={frames.length - 1}
            value={currentFrameIdx}
            onChange={(e) => {
              setIsPlaying(false);
              setCurrentFrameIdx(parseInt(e.target.value, 10));
            }}
            className="w-full accent-indigo-500 cursor-pointer h-1.5 bg-zinc-800 rounded-lg appearance-none"
          />
        </div>
        {/* Frame Pips */}
        <div className="flex justify-between px-1 mt-1">
          {frames.map((f, i) => (
            <button
              key={i}
              onClick={() => {
                setIsPlaying(false);
                setCurrentFrameIdx(i);
              }}
              title={`${f.timestamp} — ${f.title}`}
              className={`w-2 h-2 rounded-full transition-all ${
                i === currentFrameIdx
                  ? "bg-indigo-400 ring-2 ring-indigo-500 scale-125"
                  : i < currentFrameIdx
                  ? "bg-emerald-600"
                  : "bg-zinc-700 hover:bg-zinc-500"
              }`}
            />
          ))}
        </div>
      </div>

      {/* ----------------- CENTER WORKBENCH: 3D CANVAS + TELEMETRY HUD ----------------- */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-0 h-[520px]">
        {/* 3D Simulation Canvas */}
        <div className="lg:col-span-2 relative bg-[#090a0f] h-full">
          <Canvas camera={{ position: [11, 11, 11], fov: 48 }} style={{ width: "100%", height: "100%" }}>
            <CameraController preset={cameraPreset} presets={presets} />
            <ForensicScene
              frame={currentFrame}
              trajectory={simulation.trajectory}
              zones={simulation.scene_config.zones}
            />
          </Canvas>

          {/* Active Sensor Live Badge */}
          <div className="absolute top-3 left-3 bg-zinc-950/85 backdrop-blur border border-zinc-800 rounded px-2.5 py-1.5 text-[11px] shadow-lg flex items-center gap-2">
            <span
              className="w-2 h-2 rounded-full animate-ping"
              style={{ backgroundColor: currentFrame.scene_state.sensor_color || "#10b981" }}
            />
            <span className="font-mono text-zinc-300 font-semibold">{currentFrame.scene_state.active_sensor}</span>
          </div>

          {/* Camera POV Watermark */}
          <div className="absolute bottom-3 left-3 bg-zinc-900/80 backdrop-blur rounded px-2 py-1 text-[10px] text-zinc-400 font-mono">
            PERSPECTIVE: {presets[cameraPreset]?.label || "Free Orbit"}
          </div>
        </div>

        {/* Right HUD: Telemetry, Photo Reference & Contradiction Alert */}
        <div className="p-4 bg-zinc-950/95 border-t lg:border-t-0 lg:border-l border-zinc-800 flex flex-col justify-between overflow-y-auto space-y-3">
          <div>
            <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-1">
              Active Scene Narrative
            </div>
            <h3 className="text-sm font-semibold text-white mb-1.5">{currentFrame.title}</h3>
            <p className="text-xs text-zinc-300 leading-relaxed bg-zinc-900/60 p-2.5 rounded border border-zinc-800/80 mb-3">
              {currentFrame.narrative}
            </p>

            {/* ADVERSARIAL CONFLICT ALERT (PULSES IF ACTIVE AT THIS TIMESTAMP) */}
            {currentFrame.conflict_alert && (
              <div className="mb-3 p-3 rounded-lg bg-red-950/50 border border-red-700/80 shadow-lg shadow-red-950/40">
                <div className="flex items-center gap-1.5 text-xs font-bold text-red-400 mb-1">
                  <span>⚠️</span>
                  <span>{currentFrame.conflict_alert.title}</span>
                </div>
                <p className="text-[11px] text-red-200/90 leading-tight mb-2">
                  {currentFrame.conflict_alert.nature}
                </p>
                <div className="text-[10px] font-mono text-red-300/80 bg-red-900/30 p-1.5 rounded">
                  ⚖️ {currentFrame.conflict_alert.admissibility_rule}
                </div>
              </div>
            )}

            {/* Synchronized Multimodal Telemetry Cards */}
            <div className="space-y-2 text-xs">
              <div className="p-2 bg-zinc-900/50 border border-zinc-800 rounded">
                <div className="text-[10px] text-zinc-500 font-medium uppercase mb-0.5">Hardware Sensor Log</div>
                <div className="text-emerald-400 font-mono text-[11px]">{currentFrame.telemetry.sensor_event}</div>
              </div>

              <div className="p-2 bg-zinc-900/50 border border-zinc-800 rounded">
                <div className="text-[10px] text-zinc-500 font-medium uppercase mb-0.5">CCTV Camera Overlay</div>
                <div className="text-sky-300 font-mono text-[11px]">{currentFrame.telemetry.cctv_frame}</div>
              </div>

              <div className="p-2 bg-zinc-900/50 border border-zinc-800 rounded">
                <div className="text-[10px] text-zinc-500 font-medium uppercase mb-0.5">Witness / Patrol Account</div>
                <div className="text-zinc-300 italic text-[11px]">{currentFrame.telemetry.witness_statement}</div>
              </div>
            </div>
          </div>

          {/* Evidence Exhibit Association */}
          {currentFrame.evidence_markers?.length > 0 && (
            <div className="pt-2 border-t border-zinc-900">
              <div className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-1.5">
                Physical Exhibits at this Timestamp ({currentFrame.evidence_markers.length})
              </div>
              <div className="space-y-1">
                {currentFrame.evidence_markers.map((em, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-1.5 rounded bg-zinc-900 border border-zinc-800 text-[11px]"
                  >
                    <span className="font-medium text-amber-400">🏷️ {em.label}</span>
                    {em.filename && (
                      <span className="text-[10px] font-mono text-zinc-500 truncate max-w-[120px]">
                        {em.filename}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
