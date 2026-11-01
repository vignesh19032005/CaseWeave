"use client";

import React, { useRef, useEffect, useState, useMemo } from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { api } from "../lib/api";

export interface SandboxScenario {
  scenario_id: string;
  case_id: string;
  scenario_type: "automated" | "officer_custom";
  title: string;
  badge: string;
  evidence_fit_pct: number;
  hypothesis_summary: string;
  supporting_facts: string[];
  contradicted_points: string[];
  physics_validation: {
    is_physically_possible: boolean;
    total_distance_meters: number;
    avg_speed_mps: number;
    max_speed_mps: number;
    clearance_check: string;
    gravity_grounding: string;
    line_of_sight: {
      guard_to_shutter: string;
      explanation: string;
    };
    violations: string[];
  };
  frames: Array<{
    frame_idx: number;
    timestamp: string;
    phase: string;
    title: string;
    narrative: string;
    actor: { visible: boolean; pos: [number, number, number]; action: string };
    scene_state: {
      shutter_height: number;
      vault_toppled: boolean;
      counter_open: boolean;
      sensor_status: string;
    };
    evidence_marker?: { id: string; label: string; pos: [number, number, number]; photo?: string } | null;
    conflict_banner?: string;
    camera_preset?: string;
  }>;
  trajectory: Array<{ pos: [number, number, number]; label: string; dt_sec?: number }>;
  interview_qa?: Record<string, string>;
}

// Core 3 forensic viewpoints (all close-up exhibits are inspected via 100% interactive direct mesh clicks)
const CAMERA_PRESETS: Record<string, { pos: [number, number, number]; target: [number, number, number]; label: string }> = {
  overview: { pos: [12, 11, 12], target: [0, 1, 0], label: "🌐 Free 360° Orbit" },
  cctv_alley: { pos: [-5.8, 3.8, -7.5], target: [-4.5, 1.2, -5.5], label: "📹 CCTV-2 Alley Cam" },
  guard_sightline: { pos: [-8.5, 1.5, -5.5], target: [-4.5, 1.2, -6.85], label: "👁️ Guard Sightline POV" },
};

function SmoothCameraController({
  preset,
  focusTarget,
  manualZoom,
}: {
  preset: string;
  focusTarget: [number, number, number] | null;
  manualZoom: { id: number; delta: number };
}) {
  const { camera } = useThree();
  const controlsRef = useRef<any>(null);
  const targetPos = useRef(new THREE.Vector3(12, 11, 12));
  const targetLook = useRef(new THREE.Vector3(0, 1, 0));
  const isTransitioning = useRef(true);

  useEffect(() => {
    const config = CAMERA_PRESETS[preset] || CAMERA_PRESETS["overview"];
    targetPos.current.set(...config.pos);
    targetLook.current.set(...config.target);
    isTransitioning.current = true;
  }, [preset]);

  useEffect(() => {
    if (focusTarget && controlsRef.current) {
      targetLook.current.set(...focusTarget);
      targetPos.current.set(
        focusTarget[0] + (focusTarget[0] > 0 ? -3.2 : 3.2),
        focusTarget[1] + 2.0,
        focusTarget[2] + 3.2
      );
      isTransitioning.current = true;
    }
  }, [focusTarget]);

  useEffect(() => {
    if (manualZoom.id > 0 && controlsRef.current) {
      const dir = new THREE.Vector3();
      camera.getWorldDirection(dir);
      camera.position.addScaledVector(dir, manualZoom.delta * 2.5);
      controlsRef.current.update();
      isTransitioning.current = false;
    }
  }, [manualZoom, camera]);

  useFrame(() => {
    if (!isTransitioning.current) return;
    camera.position.lerp(targetPos.current, 0.08);
    if (controlsRef.current) {
      controlsRef.current.target.lerp(targetLook.current, 0.08);
      controlsRef.current.update();
    }
    if (
      camera.position.distanceTo(targetPos.current) < 0.05 &&
      controlsRef.current &&
      controlsRef.current.target.distanceTo(targetLook.current) < 0.05
    ) {
      isTransitioning.current = false;
    }
  });

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping={true}
      dampingFactor={0.08}
      enableRotate={true}
      enableZoom={true}
      enablePan={true}
      rotateSpeed={1.0}
      zoomSpeed={1.4}
      panSpeed={1.0}
      minDistance={0.5}
      maxDistance={50}
      maxPolarAngle={Math.PI / 2.02}
      touches={{
        ONE: THREE.TOUCH.ROTATE,
        TWO: THREE.TOUCH.DOLLY_PAN,
      }}
      mouseButtons={{
        LEFT: THREE.MOUSE.ROTATE,
        MIDDLE: THREE.MOUSE.DOLLY,
        RIGHT: THREE.MOUSE.PAN,
      }}
      onStart={() => {
        isTransitioning.current = false;
      }}
    />
  );
}

// ---------------------------------------------------------------------
// CONTINUOUS KINEMATICS & NAVMESH TOPOLOGICAL CORRIDOR SOLVER
// ---------------------------------------------------------------------
export interface ContinuousSimState {
  simTime: number; // 0 to 420 seconds
  clockStr: string;
  pos: [number, number, number];
  rotationY: number;
  action: "walking" | "prying" | "crawling" | "looting" | "carrying_walking" | "prying_till" | "fleeing";
  isDucking: boolean;
  shutterHeight: number;
  vaultToppled: boolean;
  vaultDoorOpen: boolean;
  boxLootCount: number; // 0 to 3 boxes placed into duffel bag
  counterTillOpen: boolean;
  duffelBagState: "none" | "floor" | "shoulder";
  crowbarState: "hand" | "floor";
  sensorStatus: string;
  phaseBadge: string;
  narrative: string;
}

function solveContinuousSimState(t: number): ContinuousSimState {
  const clampedT = Math.max(0, Math.min(420, t));
  const totalSec = 18 * 60 + clampedT; // Starts at 02:18:00 AM
  const hh = "02";
  const mm = String(Math.floor(totalSec / 60)).padStart(2, "0");
  const ss = String(Math.floor(totalSec % 60)).padStart(2, "0");
  const clockStr = `${hh}:${mm}:${ss} AM`;

  let pos: [number, number, number] = [-4.5, 0, -8.8];
  let rotationY = 0;
  let action: ContinuousSimState["action"] = "walking";
  let isDucking = false;
  let shutterHeight = 0.0;
  let vaultToppled = false;
  let vaultDoorOpen = false;
  let boxLootCount = 0;
  let counterTillOpen = false;
  let duffelBagState: ContinuousSimState["duffelBagState"] = "none";
  let crowbarState: ContinuousSimState["crowbarState"] = "hand";
  let sensorStatus = "Perimeter CCTV Active";
  let phaseBadge = "Alleyway Infiltration Approach";
  let narrative = "Suspect approaches stealthily along the rear alleyway strictly outside the perimeter wall.";

  if (clampedT < 45) {
    // 1. Alley Approach: [-4.5, 0, -8.8] to [-4.5, 0, -7.5]
    const a = clampedT / 45;
    pos = [-4.5, 0, -8.8 + a * 1.3];
    rotationY = 0;
    action = "walking";
    shutterHeight = 0.0;
    phaseBadge = "🚶 Alleyway Approach (Outside Walls)";
    narrative = "Suspect moves north along the rear alleyway toward Gate-B, remaining in the alley blindspot.";
  } else if (clampedT < 90) {
    // 2. Shutter Prying at [-4.5, 0, -7.5] (outside wall)
    pos = [-4.5, 0, -7.5];
    rotationY = 0;
    action = "prying";
    const pryProg = Math.max(0, Math.min(1, (clampedT - 60) / 30));
    shutterHeight = pryProg * 0.95;
    sensorStatus = clampedT >= 70 ? "TAMPER SWITCH ALARM" : "Approaching Clasp";
    phaseBadge = "🔧 Prying Gate-B Shutter Clasp with Crowbar";
    narrative = "Suspect stands outside the shutter, inserts blue 18-inch crowbar into bottom clasp, applying leverage until the shutter lifts to 0.95m clearance.";
  } else if (clampedT < 120) {
    // 3. Aperture Clearance Entry: [-4.5, 0, -7.5] -> [-4.5, 0, -5.8]
    const a = (clampedT - 90) / 30;
    pos = [-4.5, 0, -7.5 + a * 1.7];
    rotationY = 0;
    action = "crawling";
    isDucking = true;
    shutterHeight = 0.95;
    sensorStatus = "BREACH CONFIRMED (Tamper RFID-01)";
    phaseBadge = "🧎 Crawling Under 0.95m Shutter Aperture";
    narrative = "Suspect crouches low to 0.55m height, clearing through the 0.95m opening without any wall or frame clipping.";
  } else if (clampedT < 165) {
    // 4. North Aisle Transit: [-4.5, 0, -5.8] -> [-1.0, 0, -5.5] -> [3.2, 0, -2.5]
    const a = (clampedT - 120) / 45;
    shutterHeight = 0.95;
    action = "walking";
    if (a < 0.5) {
      const sub = a / 0.5;
      pos = [-4.5 + sub * 3.5, 0, -5.8 + sub * 0.3];
      rotationY = Math.PI / 2;
    } else {
      const sub = (a - 0.5) / 0.5;
      pos = [-1.0 + sub * 4.2, 0, -5.5 + sub * 3.0];
      rotationY = Math.PI / 4;
    }
    sensorStatus = "Aisle Transit (Hugging PIR Deadzone)";
    phaseBadge = "🚶 Navigating North Storage Aisle";
    narrative = "Suspect navigates along the clear north corridor between shelves and rear wall, staying under the PIR motion detector cone.";
  } else if (clampedT < 270) {
    // 5. Narcotics Vault Breach & Bag Packing: At [3.2, 0, -2.5]
    pos = [3.2, 0, -2.5];
    rotationY = Math.PI / 2;
    action = "looting";
    shutterHeight = 0.95;
    vaultToppled = clampedT >= 185;
    vaultDoorOpen = clampedT >= 195;
    duffelBagState = "floor";
    if (clampedT >= 200 && clampedT < 225) boxLootCount = 1;
    else if (clampedT >= 225 && clampedT < 250) boxLootCount = 2;
    else if (clampedT >= 250) boxLootCount = 3;

    sensorStatus = "VAULT DOOR SENSOR TRIGGERED";
    phaseBadge = "🎒 Looting Narcotics Safe & Packing Duffel Bag";
    narrative = "Safe dial is forced; upper glass cabinet topples. Suspect unzips black duffel bag on the floor and packs 120 units of controlled narcotics cartons.";
  } else if (clampedT < 315) {
    // 6. Showroom Transit to Billing Desk: [3.2, 0, -2.5] -> [0.6, 0, 0.5] -> [2.0, 0, 3.2]
    const a = (clampedT - 270) / 45;
    shutterHeight = 0.95;
    vaultToppled = true;
    vaultDoorOpen = true;
    boxLootCount = 3;
    duffelBagState = "shoulder";
    action = "carrying_walking";
    if (a < 0.5) {
      const sub = a / 0.5;
      pos = [3.2 - sub * 2.6, 0, -2.5 + sub * 3.0];
      rotationY = Math.PI;
    } else {
      const sub = (a - 0.5) / 0.5;
      pos = [0.6 + sub * 1.4, 0, 0.5 + sub * 2.7];
      rotationY = 0;
    }
    sensorStatus = "Showroom Floor Motion Active";
    phaseBadge = "🚶 Carrying Loaded Duffel Bag to Billing Desk";
    narrative = "Suspect slings the loaded duffel bag over left shoulder and walks down the central aisle toward the retail counter.";
  } else if (clampedT < 360) {
    // 7. Cash Till Drawer Pried: At [2.0, 0, 3.2]
    pos = [2.0, 0, 3.2];
    rotationY = Math.PI / 2;
    action = "prying_till";
    shutterHeight = 0.95;
    vaultToppled = true;
    vaultDoorOpen = true;
    boxLootCount = 3;
    duffelBagState = "shoulder";
    counterTillOpen = clampedT >= 330;
    crowbarState = clampedT >= 345 ? "floor" : "hand";
    sensorStatus = "TILL REED SWITCH TAMPER";
    phaseBadge = "💵 Prying Cash Till Drawer & Stealing Float";
    narrative = "Suspect jimmies the register till; cash float of INR 45,000 is grabbed. Crowbar slips and drops onto concrete floor beside till with blue nitrile glove.";
  } else {
    // 8. Egress via Corridors: [2.0, 0, 3.2] -> [0.6, 0, -5.5] -> [-4.5, 0, -5.8] -> crawl [-4.5, 0, -7.5] -> flee [-4.5, 0, -9.2]
    const a = (clampedT - 360) / 60;
    shutterHeight = 0.95;
    vaultToppled = true;
    vaultDoorOpen = true;
    boxLootCount = 3;
    counterTillOpen = true;
    duffelBagState = "shoulder";
    crowbarState = "floor";

    if (a < 0.35) {
      const sub = a / 0.35;
      pos = [2.0 - sub * 1.4, 0, 3.2 - sub * 8.7];
      rotationY = -Math.PI;
      action = "carrying_walking";
    } else if (a < 0.65) {
      const sub = (a - 0.35) / 0.3;
      pos = [0.6 - sub * 5.1, 0, -5.5 - sub * 0.3];
      rotationY = -Math.PI / 2;
      action = "carrying_walking";
    } else if (a < 0.82) {
      const sub = (a - 0.65) / 0.17;
      pos = [-4.5, 0, -5.8 - sub * 1.7];
      rotationY = -Math.PI;
      action = "crawling";
      isDucking = true;
    } else {
      const sub = (a - 0.82) / 0.18;
      pos = [-4.5, 0, -7.5 - sub * 1.7];
      rotationY = -Math.PI;
      action = "fleeing";
    }
    sensorStatus = "EGRESS COMPLETED (02:25 AM)";
    phaseBadge = "🏃 Corridors Egress & Alleyway Flight";
    narrative = "Suspect ducks back under the Gate-B shutter opening into the alley with the duffel bag, fleeing north toward EVR Salai.";
  }

  return {
    simTime: clampedT,
    clockStr,
    pos,
    rotationY,
    action,
    isDucking,
    shutterHeight,
    vaultToppled,
    vaultDoorOpen,
    boxLootCount,
    counterTillOpen,
    duffelBagState,
    crowbarState,
    sensorStatus,
    phaseBadge,
    narrative,
  };
}

// ---------------------------------------------------------------------
// ARTICULATED KINEMATIC CHARACTER MESH
// ---------------------------------------------------------------------
function KinematicSuspectAvatar({
  simState,
  onObjectClick,
}: {
  simState: ContinuousSimState;
  onObjectClick: (obj: any) => void;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const leftLegRef = useRef<THREE.Group>(null);
  const rightLegRef = useRef<THREE.Group>(null);
  const leftArmRef = useRef<THREE.Group>(null);
  const rightArmRef = useRef<THREE.Group>(null);

  // Smooth position & rotation
  useFrame(() => {
    if (groupRef.current) {
      groupRef.current.position.set(...simState.pos);
      groupRef.current.rotation.y = simState.rotationY;

      const t = simState.simTime;
      const isMoving = simState.action === "walking" || simState.action === "carrying_walking" || simState.action === "fleeing";
      const strideFreq = simState.action === "fleeing" ? 11 : 7;

      // Leg Swing
      if (isMoving && leftLegRef.current && rightLegRef.current) {
        const legAngle = Math.sin(t * strideFreq) * 0.45;
        leftLegRef.current.rotation.x = legAngle;
        rightLegRef.current.rotation.x = -legAngle;
      } else if (leftLegRef.current && rightLegRef.current) {
        leftLegRef.current.rotation.x = 0;
        rightLegRef.current.rotation.x = 0;
      }

      // Arm Swing & Action Gestures
      if (leftArmRef.current && rightArmRef.current) {
        if (simState.action === "prying") {
          // Both arms forward holding crowbar
          leftArmRef.current.rotation.x = -1.1 + Math.sin(t * 4) * 0.15;
          rightArmRef.current.rotation.x = -1.1 + Math.sin(t * 4) * 0.15;
        } else if (simState.action === "looting") {
          // Transferring cartons into duffel bag
          leftArmRef.current.rotation.x = -0.6 + Math.sin(t * 3) * 0.5;
          rightArmRef.current.rotation.x = -0.9 + Math.cos(t * 3) * 0.5;
        } else if (simState.action === "crawling") {
          leftArmRef.current.rotation.x = -1.4;
          rightArmRef.current.rotation.x = -1.4;
        } else if (isMoving) {
          const armAngle = Math.sin(t * strideFreq) * 0.4;
          leftArmRef.current.rotation.x = -armAngle;
          rightArmRef.current.rotation.x = armAngle;
        } else {
          leftArmRef.current.rotation.x = 0;
          rightArmRef.current.rotation.x = 0;
        }
      }
    }
  });

  const isDucking = simState.isDucking;
  const isKneeling = simState.action === "prying" || simState.action === "looting";

  return (
    <group
      ref={groupRef}
      onClick={(e) => {
        e.stopPropagation();
        onObjectClick({
          name: "Suspect Silhouette (Articulated Rig)",
          category: "Physical Kinematics Reconstruction",
          description: "Reconstructed actor with human joint biomechanics. Navigates strictly along collision-free topological corridors without wall clipping.",
          focusPos: simState.pos,
        });
      }}
      onPointerOver={() => (document.body.style.cursor = "pointer")}
      onPointerOut={() => (document.body.style.cursor = "auto")}
    >
      {/* Ground Footprint Shadow */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
        <circleGeometry args={[0.42, 32]} />
        <meshBasicMaterial color="#000000" transparent opacity={0.55} />
      </mesh>

      {/* Main Pelvis Pivot */}
      <group position={[0, isDucking ? 0.42 : isKneeling ? 0.55 : 0.85, 0]}>
        {/* Torso: Dark Hooded Windbreaker Jacket */}
        <mesh position={[0, 0.35, 0]} rotation={[isDucking ? 0.6 : 0.08, 0, 0]}>
          <capsuleGeometry args={[0.24, 0.5, 8, 16]} />
          <meshStandardMaterial color="#1e293b" roughness={0.45} />
        </mesh>

        {/* Head & Hood */}
        <mesh position={[0, isDucking ? 0.65 : 0.85, isDucking ? 0.3 : 0]}>
          <sphereGeometry args={[0.2, 16, 16]} />
          <meshStandardMaterial color="#0f172a" roughness={0.5} />
        </mesh>

        {/* Left Arm Pivot */}
        <group ref={leftArmRef} position={[-0.3, 0.45, 0]}>
          <mesh position={[0, -0.3, 0]}>
            <capsuleGeometry args={[0.07, 0.45, 8, 8]} />
            <meshStandardMaterial color="#1e293b" />
          </mesh>
          {/* Hand */}
          <mesh position={[0, -0.55, 0]}>
            <sphereGeometry args={[0.065, 8, 8]} />
            <meshStandardMaterial color="#0f172a" />
          </mesh>
        </group>

        {/* Right Arm Pivot */}
        <group ref={rightArmRef} position={[0.3, 0.45, 0]}>
          <mesh position={[0, -0.3, 0]}>
            <capsuleGeometry args={[0.07, 0.45, 8, 8]} />
            <meshStandardMaterial color="#1e293b" />
          </mesh>
          {/* Hand */}
          <mesh position={[0, -0.55, 0]}>
            <sphereGeometry args={[0.065, 8, 8]} />
            <meshStandardMaterial color="#0f172a" />
          </mesh>

          {/* Crowbar held in right hand */}
          {simState.crowbarState === "hand" && (
            <mesh position={[0, -0.55, 0.25]} rotation={[Math.PI / 3, 0, 0]}>
              <boxGeometry args={[0.05, 0.04, 0.75]} />
              <meshStandardMaterial color="#0284c7" metalness={0.85} roughness={0.2} />
            </mesh>
          )}
        </group>

        {/* Duffel Bag Slung Over Shoulder */}
        {simState.duffelBagState === "shoulder" && (
          <group position={[-0.32, 0.2, -0.1]} rotation={[0.2, 0.3, -0.4]}>
            {/* Duffel Cylinder */}
            <mesh>
              <capsuleGeometry args={[0.16, 0.45, 8, 16]} />
              <meshStandardMaterial color="#0f172a" roughness={0.8} />
            </mesh>
            {/* Shoulder Strap Across Chest */}
            <mesh position={[0.25, 0.1, 0.15]} rotation={[0, 0, -Math.PI / 4]}>
              <boxGeometry args={[0.04, 0.65, 0.015]} />
              <meshStandardMaterial color="#334155" />
            </mesh>
          </group>
        )}
      </group>

      {/* Left Leg Pivot */}
      <group ref={leftLegRef} position={[-0.14, isDucking ? 0.42 : isKneeling ? 0.55 : 0.85, 0]}>
        <mesh position={[0, -0.42, 0]}>
          <cylinderGeometry args={[0.08, 0.07, 0.75, 8]} />
          <meshStandardMaterial color="#090d16" />
        </mesh>
        {/* White Sports Shoe */}
        <mesh position={[0, -0.8, 0.08]}>
          <boxGeometry args={[0.12, 0.09, 0.25]} />
          <meshStandardMaterial color="#f8fafc" roughness={0.3} />
        </mesh>
      </group>

      {/* Right Leg Pivot */}
      <group ref={rightLegRef} position={[0.14, isDucking ? 0.42 : isKneeling ? 0.55 : 0.85, 0]}>
        <mesh position={[0, -0.42, 0]}>
          <cylinderGeometry args={[0.08, 0.07, 0.75, 8]} />
          <meshStandardMaterial color="#090d16" />
        </mesh>
        {/* White Sports Shoe */}
        <mesh position={[0, -0.8, 0.08]}>
          <boxGeometry args={[0.12, 0.09, 0.25]} />
          <meshStandardMaterial color="#f8fafc" roughness={0.3} />
        </mesh>
      </group>
    </group>
  );
}

// ---------------------------------------------------------------------
// REALISTIC ROOM ENVIRONMENT WITH BRIGHT LIGHTING & PHYSICAL ASSETS
// ---------------------------------------------------------------------
function RealisticRoomEnvironment({
  simState,
  onObjectClick,
  selectedObject,
  showGuardSightline,
}: {
  simState: ContinuousSimState;
  onObjectClick: (obj: any) => void;
  selectedObject: string | null;
  showGuardSightline: boolean;
}) {
  const shutterHeight = simState.shutterHeight;
  const isVaultToppled = simState.vaultToppled;
  const isVaultDoorOpen = simState.vaultDoorOpen;
  const isCounterOpen = simState.counterTillOpen;
  const sensorStatus = simState.sensorStatus;

  return (
    <group>
      {/* ----------------- 1. BRILLIANT DAYLIGHT ILLUMINATION ----------------- */}
      <ambientLight intensity={0.95} />
      <directionalLight position={[10, 20, 10]} intensity={1.3} castShadow />
      <directionalLight position={[-10, 16, -10]} intensity={0.9} />

      {/* 3 Overhead Fluorescent Ceiling Strip Lights (Commercial Daylight 5000K) */}
      <pointLight position={[0, 3.8, -4.0]} intensity={2.0} distance={18} color="#f8fafc" />
      <pointLight position={[0, 3.8, 0.5]} intensity={2.0} distance={18} color="#f8fafc" />
      <pointLight position={[0, 3.8, 5.0]} intensity={2.0} distance={18} color="#f8fafc" />
      {/* Exterior Streetlamp Light illuminating alley */}
      <pointLight position={[-4.5, 3.8, -8.5]} intensity={2.2} distance={15} color="#fef08a" />

      {/* Status Alert Spotlights */}
      <pointLight position={[-4.5, 3.2, -6.0]} intensity={sensorStatus.includes("ALARM") ? 2.5 : 0.8} color={sensorStatus.includes("ALARM") ? "#ef4444" : "#f8fafc"} />
      <pointLight position={[3.8, 3.0, -2.5]} intensity={isVaultToppled ? 2.2 : 0.9} color={isVaultToppled ? "#f59e0b" : "#38bdf8"} />
      <pointLight position={[2.2, 2.5, 3.8]} intensity={isCounterOpen ? 2.2 : 0.8} color={isCounterOpen ? "#ef4444" : "#ffffff"} />

      {/* Visible Overhead Fluorescent Light Tubes */}
      {[-4.0, 0.5, 5.0].map((zPos, idx) => (
        <group key={idx} position={[0, 3.65, zPos]}>
          <mesh>
            <boxGeometry args={[4.2, 0.08, 0.35]} />
            <meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={1.4} />
          </mesh>
        </group>
      ))}

      {/* Clean Commercial Epoxy/Tile Floor (High Visibility) */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]}>
        <planeGeometry args={[18, 22]} />
        <meshStandardMaterial color="#94a3b8" roughness={0.4} metalness={0.2} />
      </mesh>
      <gridHelper args={[24, 24, "#475569", "#64748b"]} position={[0, 0.001, 0]} />

      {/* ----------------- 2. ARCHITECTURAL WALLS & CORRIDORS ----------------- */}
      {/* Rear Brick Alley Wall (Boundary at z = -7.1m) */}
      <mesh position={[0, 1.6, -7.1]}>
        <boxGeometry args={[16, 3.2, 0.4]} />
        <meshStandardMaterial color="#64748b" roughness={0.7} metalness={0.1} />
      </mesh>
      {/* Left Wall Cutaway */}
      <mesh position={[-7.8, 1.0, 0]}>
        <boxGeometry args={[0.4, 2.0, 14]} />
        <meshStandardMaterial color="#475569" transparent opacity={0.6} />
      </mesh>
      {/* Right Wall Cutaway */}
      <mesh position={[7.8, 1.0, 0]}>
        <boxGeometry args={[0.4, 2.0, 14]} />
        <meshStandardMaterial color="#475569" transparent opacity={0.6} />
      </mesh>

      {/* ----------------- 3. GATE-B ROLLING SHUTTER (CLICKABLE) ----------------- */}
      <group
        position={[-4.5, 0, -6.9]}
        onClick={(e) => {
          e.stopPropagation();
          onObjectClick({
            name: "Gate-B Rolling Shutter",
            category: "Point of Forced Entry",
            description: "Corrugated steel rolling shutter. Pried from bottom center clasp with 18-inch crowbar. Lifted ~0.95m clearance off concrete apron.",
            photoRef: "01_tampered_rear_shutter.jpg",
            focusPos: [-4.5, 1.2, -6.9],
          });
        }}
        onPointerOver={() => (document.body.style.cursor = "pointer")}
        onPointerOut={() => (document.body.style.cursor = "auto")}
      >
        {/* Steel Guide Posts */}
        <mesh position={[-1.6, 1.6, 0]}>
          <boxGeometry args={[0.25, 3.2, 0.25]} />
          <meshStandardMaterial color="#cbd5e1" metalness={0.8} roughness={0.3} />
        </mesh>
        <mesh position={[1.6, 1.6, 0]}>
          <boxGeometry args={[0.25, 3.2, 0.25]} />
          <meshStandardMaterial color="#cbd5e1" metalness={0.8} roughness={0.3} />
        </mesh>
        {/* Housing Header Box */}
        <mesh position={[0, 3.25, 0]}>
          <boxGeometry args={[3.45, 0.35, 0.35]} />
          <meshStandardMaterial color="#64748b" metalness={0.7} />
        </mesh>

        {/* Dynamic Corrugated Slats (Raises with shutterHeight) */}
        <mesh position={[0, 1.6 + shutterHeight / 2, 0]}>
          <boxGeometry args={[2.95, Math.max(0.1, 3.0 - shutterHeight), 0.08]} />
          <meshStandardMaterial
            color={selectedObject === "Gate-B Rolling Shutter" ? "#fbbf24" : shutterHeight > 0.2 ? "#ef4444" : "#cbd5e1"}
            metalness={0.8}
            roughness={0.35}
          />
        </mesh>

        {/* Sheared Padlock on Floor Apron */}
        <mesh position={[0, 0.08, 0.3]}>
          <boxGeometry args={[0.2, 0.12, 0.15]} />
          <meshStandardMaterial color="#d97706" metalness={0.9} roughness={0.2} />
        </mesh>

        {/* Tamper Switch LED Beacon */}
        <mesh position={[0, 3.5, 0.2]}>
          <sphereGeometry args={[0.1, 16, 16]} />
          <meshStandardMaterial
            color={sensorStatus.includes("ALARM") || sensorStatus.includes("BREACH") ? "#ef4444" : "#10b981"}
            emissive={sensorStatus.includes("ALARM") || sensorStatus.includes("BREACH") ? "#ef4444" : "#10b981"}
            emissiveIntensity={2.0}
          />
        </mesh>
      </group>

      {/* ----------------- 4. CCTV-ALLEY-02 CAMERA (CLICKABLE) ----------------- */}
      <group
        position={[-6.5, 3.4, -6.9]}
        rotation={[0.35, 0.55, 0]}
        onClick={(e) => {
          e.stopPropagation();
          onObjectClick({
            name: "CCTV-ALLEY-02 Camera",
            category: "Electronic Surveillance Exhibit",
            description: "High-definition monochrome IR alleyway camera. Timestamp overlay had +5m 12s uncalibrated DVR clock drift.",
            photoRef: "03_cctv_alleyway_log.txt",
            focusPos: [-6.5, 3.4, -6.9],
          });
        }}
        onPointerOver={() => (document.body.style.cursor = "pointer")}
        onPointerOut={() => (document.body.style.cursor = "auto")}
      >
        <mesh>
          <boxGeometry args={[0.35, 0.35, 0.8]} />
          <meshStandardMaterial color="#f8fafc" metalness={0.8} />
        </mesh>
        <mesh position={[0, 0, 0.45]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.12, 0.12, 0.1, 16]} />
          <meshStandardMaterial color="#0284c7" emissive="#0284c7" emissiveIntensity={1.0} />
        </mesh>
      </group>

      {/* ----------------- 5. PHARMACY STORAGE SHELVES (STOCKROOM) ----------------- */}
      <group position={[-2.2, 0, -2.0]}>
        {/* Metal Rack Frame */}
        <mesh position={[0, 1.5, 0]}>
          <boxGeometry args={[0.7, 3.0, 4.0]} />
          <meshStandardMaterial color="#475569" metalness={0.5} roughness={0.5} />
        </mesh>
        {/* Stocked Medicine Cartons on Shelves */}
        {[-1.2, 0, 1.2].map((zOffset, i) => (
          <group key={i} position={[0, 0.8 + i * 0.8, zOffset]}>
            <mesh position={[0.15, 0, 0]}>
              <boxGeometry args={[0.35, 0.3, 0.7]} />
              <meshStandardMaterial color={i === 0 ? "#38bdf8" : i === 1 ? "#fbbf24" : "#f87171"} />
            </mesh>
            <mesh position={[-0.15, 0, 0]}>
              <boxGeometry args={[0.35, 0.3, 0.7]} />
              <meshStandardMaterial color="#f1f5f9" />
            </mesh>
          </group>
        ))}
      </group>

      {/* ----------------- 6. GODREJ NARCOTICS VAULT & MEDICINE SAFE ----------------- */}
      <group
        position={[3.8, 0, -2.5]}
        onClick={(e) => {
          e.stopPropagation();
          onObjectClick({
            name: "High-Value Narcotics Vault",
            category: "Primary Target of Theft",
            description: "Godrej Grade-B double-walled narcotics safe. Dual keyhole & digital dial forced open. 120 units controlled pharmaceuticals missing.",
            photoRef: "02_toppled_narcotics_cabinet.jpg",
            focusPos: [3.8, 1.0, -2.5],
          });
        }}
        onPointerOver={() => (document.body.style.cursor = "pointer")}
        onPointerOut={() => (document.body.style.cursor = "auto")}
      >
        {/* Main Steel Safe Body */}
        <mesh position={[0, 0.9, 0]}>
          <boxGeometry args={[1.4, 1.8, 1.2]} />
          <meshStandardMaterial color="#334155" metalness={0.8} roughness={0.25} />
        </mesh>

        {/* Revolving Safe Door on Hinge */}
        <group position={[-0.7, 0.9, 0.6]} rotation={[0, isVaultDoorOpen ? -1.5 : 0, 0]}>
          <mesh position={[0.7, 0, 0]}>
            <boxGeometry args={[1.35, 1.7, 0.12]} />
            <meshStandardMaterial color="#1e293b" metalness={0.85} roughness={0.2} />
          </mesh>
          {/* Chrome Digital Keypad / Dial */}
          <mesh position={[0.7, 0.2, 0.1]}>
            <cylinderGeometry args={[0.15, 0.15, 0.05, 16]} />
            <meshStandardMaterial color="#f8fafc" metalness={0.9} />
          </mesh>
        </group>

        {/* Pharmaceutical Packages inside safe (Disappear one-by-one as packed into duffel bag) */}
        {simState.boxLootCount < 1 && (
          <mesh position={[-0.2, 1.2, 0]}>
            <boxGeometry args={[0.3, 0.25, 0.4]} />
            <meshStandardMaterial color="#f87171" />
          </mesh>
        )}
        {simState.boxLootCount < 2 && (
          <mesh position={[0.2, 1.2, 0]}>
            <boxGeometry args={[0.3, 0.25, 0.4]} />
            <meshStandardMaterial color="#fbbf24" />
          </mesh>
        )}
        {simState.boxLootCount < 3 && (
          <mesh position={[0.0, 0.6, 0]}>
            <boxGeometry args={[0.4, 0.25, 0.4]} />
            <meshStandardMaterial color="#38bdf8" />
          </mesh>
        )}

        {/* Toppled Glass Upper Cabinet */}
        <group
          position={[0.2, 2.0, 0]}
          rotation={isVaultToppled ? [0.4, 0.2, 1.45] : [0, 0, 0]}
        >
          <mesh>
            <boxGeometry args={[1.2, 0.9, 0.8]} />
            <meshStandardMaterial color="#0284c7" transparent opacity={0.4} roughness={0.1} />
          </mesh>
        </group>
      </group>

      {/* ----------------- 7. INTERACTIVE DUFFEL BAG (ON FLOOR AT SAFE) ----------------- */}
      {simState.duffelBagState === "floor" && (
        <group position={[2.8, 0.18, -2.0]} rotation={[0, 0.4, 0]}>
          {/* Black Canvas Duffel Cylinder */}
          <mesh>
            <capsuleGeometry args={[0.18, 0.55, 8, 16]} />
            <meshStandardMaterial color="#090d16" roughness={0.7} />
          </mesh>
          {/* Open Zipper Gap & Interior */}
          <mesh position={[0, 0.17, 0]}>
            <boxGeometry args={[0.1, 0.02, 0.4]} />
            <meshStandardMaterial color="#fbbf24" />
          </mesh>
          {/* Looted Carton inside Duffel */}
          {simState.boxLootCount > 0 && (
            <mesh position={[0, 0.1, 0]}>
              <boxGeometry args={[0.2, 0.18, 0.3]} />
              <meshStandardMaterial color="#f87171" />
            </mesh>
          )}
        </group>
      )}

      {/* ----------------- 8. BILLING DESK & SLIDING CASH TILL ----------------- */}
      <group
        position={[2.2, 0, 3.8]}
        onClick={(e) => {
          e.stopPropagation();
          onObjectClick({
            name: "Front Billing Counter & Till",
            category: "Secondary Target of Theft",
            description: "Wooden retail counter desk. Cash register pried open; cash float stolen. Crowbar slipped and dropped on floor beside till.",
            photoRef: "04_cash_drawer_and_counter.jpg",
            focusPos: [2.2, 0.9, 3.8],
          });
        }}
        onPointerOver={() => (document.body.style.cursor = "pointer")}
        onPointerOut={() => (document.body.style.cursor = "auto")}
      >
        {/* Wooden L-Desk */}
        <mesh position={[0, 0.55, 0]}>
          <boxGeometry args={[3.0, 1.1, 1.2]} />
          <meshStandardMaterial color="#78350f" roughness={0.6} />
        </mesh>
        {/* POS Computer Terminal */}
        <mesh position={[-0.8, 1.35, 0]}>
          <boxGeometry args={[0.1, 0.45, 0.65]} />
          <meshStandardMaterial color="#0f172a" />
        </mesh>
        {/* Cash Register & Sliding Till Drawer */}
        <mesh position={[0.6, 0.9, isCounterOpen ? 0.85 : 0.45]}>
          <boxGeometry args={[0.8, 0.22, 0.6]} />
          <meshStandardMaterial color={isCounterOpen ? "#ef4444" : "#475569"} metalness={0.6} />
        </mesh>
      </group>

      {/* ----------------- 9. EVIDENCE MARKER #1 (CROWBAR & GLOVE ON FLOOR) ----------------- */}
      {simState.crowbarState === "floor" && (
        <group
          position={[1.6, 0, 2.6]}
          onClick={(e) => {
            e.stopPropagation();
            onObjectClick({
              name: "Evidence Marker #1",
              category: "Physical Evidence Exhibit",
              description: "18-inch rusted iron crowbar with blue paint scrapings, and a single blue nitrile surgical glove discarded on concrete floor.",
              photoRef: "03_discarded_crowbar_and_glove.jpg",
              focusPos: [1.6, 0.1, 2.6],
            });
          }}
          onPointerOver={() => (document.body.style.cursor = "pointer")}
          onPointerOut={() => (document.body.style.cursor = "auto")}
        >
          {/* Classic Yellow Forensic A-Frame Tent */}
          <mesh position={[0, 0.15, 0]} rotation={[0, Math.PI / 4, 0]}>
            <coneGeometry args={[0.18, 0.3, 4]} />
            <meshStandardMaterial color="#facc15" roughness={0.3} />
          </mesh>
          {/* Discarded Blue Crowbar on Floor */}
          <mesh position={[0.4, 0.03, -0.2]} rotation={[0, 0.5, 0]}>
            <boxGeometry args={[0.06, 0.04, 0.85]} />
            <meshStandardMaterial color="#0284c7" metalness={0.8} />
          </mesh>
          {/* Blue Nitrile Glove on Floor */}
          <mesh position={[0.3, 0.02, 0.2]}>
            <boxGeometry args={[0.2, 0.02, 0.25]} />
            <meshStandardMaterial color="#2563eb" roughness={0.9} />
          </mesh>
        </group>
      )}

      {/* ----------------- 10. SECURITY GUARD BOOTH & SIGHTLINE ----------------- */}
      <group
        position={[-8.5, 0, -5.5]}
        onClick={(e) => {
          e.stopPropagation();
          onObjectClick({
            name: "Night Guard Booth (K. Sundaram)",
            category: "Witness Observation Post",
            description: "Security guard seated drinking tea at 02:15 AM. Brick alley corner blocks line-of-sight to the shutter clasp, but metallic screeches were clearly audible.",
            photoRef: "04_witness_statement_sundaram.txt",
            focusPos: [-8.5, 1.2, -5.5],
          });
        }}
        onPointerOver={() => (document.body.style.cursor = "pointer")}
        onPointerOut={() => (document.body.style.cursor = "auto")}
      >
        <mesh position={[0, 1.2, 0]}>
          <boxGeometry args={[1.5, 2.4, 1.5]} />
          <meshStandardMaterial color="#1e293b" transparent opacity={0.7} />
        </mesh>
        {showGuardSightline && (
          <mesh position={[2.0, 1.2, -0.6]} rotation={[0, -0.3, 0]}>
            <coneGeometry args={[1.2, 4.5, 16]} />
            <meshBasicMaterial color="#ef4444" transparent opacity={0.25} />
          </mesh>
        )}
      </group>

      {/* ----------------- 11. ARTICULATED KINEMATIC SUSPECT AVATAR ----------------- */}
      <KinematicSuspectAvatar simState={simState} onObjectClick={onObjectClick} />
    </group>
  );
}

// ---------------------------------------------------------------------
// MAIN PLAYER COMPONENT WITH TIME SCRUBBER & CONTINUOUS PLAYBACK
// ---------------------------------------------------------------------
export default function ForensicSandboxPlayer({
  scenarios,
  caseId,
  onGenerateCustomScenario,
}: {
  scenarios: SandboxScenario[];
  caseId: string;
  onGenerateCustomScenario: (hypothesis: string, answers: Record<string, string>) => Promise<any>;
}) {
  const [activeScenarioIdx, setActiveScenarioIdx] = useState(0);
  const [simTime, setSimTime] = useState(0); // 0 to 420 seconds
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(2); // Default 2x speed for smooth realistic pacing
  const [cameraPreset, setCameraPreset] = useState("overview");
  const [showGuardSightline, setShowGuardSightline] = useState(false);

  // Interactive Camera & Zoom Controls
  const [manualZoomTrigger, setManualZoomTrigger] = useState<{ id: number; delta: number }>({ id: 0, delta: 0 });
  const [cameraFocusTarget, setCameraFocusTarget] = useState<[number, number, number] | null>(null);

  // Inspector Popover for clicked 3D objects
  const [inspectedObject, setInspectedObject] = useState<{
    name: string;
    category: string;
    description: string;
    photoRef?: string;
    focusPos?: [number, number, number];
  } | null>(null);

  // Custom Scenario Modal & Socratic Interview States
  const [showCustomModal, setShowCustomModal] = useState(false);
  const [customHypothesis, setCustomHypothesis] = useState("");
  const [interviewQuestions, setInterviewQuestions] = useState<any[]>([]);
  const [interviewAnswers, setInterviewAnswers] = useState<Record<string, string>>({});
  const [interviewLoading, setInterviewLoading] = useState(false);
  const [synthesizing, setSynthesizing] = useState(false);

  // Continuous Simulation State Solver
  const simState = useMemo(() => {
    return solveContinuousSimState(simTime);
  }, [simTime]);

  // Real-time playback loop (updates every 50ms)
  useEffect(() => {
    if (!isPlaying) return;
    const intervalMs = 50;
    const timer = setInterval(() => {
      setSimTime((prev) => {
        if (prev >= 420) {
          setIsPlaying(false);
          return 420;
        }
        return prev + (intervalMs / 1000) * playbackSpeed;
      });
    }, intervalMs);
    return () => clearInterval(timer);
  }, [isPlaying, playbackSpeed]);

  const currentScenario = scenarios[activeScenarioIdx] || scenarios[0];

  const handleSelectScenario = (idx: number) => {
    setActiveScenarioIdx(idx);
    setSimTime(0);
    setIsPlaying(false);
    setInspectedObject(null);
    setCameraFocusTarget(null);
  };

  const handleStartInterview = async () => {
    if (!customHypothesis.trim()) return;
    setInterviewLoading(true);
    try {
      const res = (await api.interviewCustomScenario(caseId, customHypothesis)) as any;
      if (res && res.questions) {
        setInterviewQuestions(res.questions);
      }
    } catch (e) {
      console.error("Interview failed:", e);
    } finally {
      setInterviewLoading(false);
    }
  };

  const handleSynthesizeScenario = async () => {
    setSynthesizing(true);
    try {
      await onGenerateCustomScenario(customHypothesis, interviewAnswers);
      setShowCustomModal(false);
      setCustomHypothesis("");
      setInterviewQuestions([]);
      setInterviewAnswers({});
    } catch (e) {
      console.error("Synthesis failed:", e);
    } finally {
      setSynthesizing(false);
    }
  };

  if (!scenarios || scenarios.length === 0) {
    return (
      <div className="border border-zinc-800 rounded-xl bg-zinc-950 p-12 text-center text-zinc-500 text-sm">
        <div className="animate-spin w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full mx-auto mb-3" />
        Loading forensically verified scenarios & 3D digital twin...
      </div>
    );
  }

  return (
    <div className="flex flex-col border border-zinc-800 rounded-xl bg-zinc-950 overflow-hidden shadow-2xl select-none">
      {/* ----------------- TOP SCENARIO SELECTOR ----------------- */}
      <div className="p-3 bg-zinc-900 border-b border-zinc-800 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[10px] text-zinc-400 font-bold uppercase tracking-wider mr-1">
            Investigative Scenarios:
          </span>
          {scenarios.map((scen, idx) => (
            <button
              key={scen.scenario_id}
              onClick={() => handleSelectScenario(idx)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition ${
                activeScenarioIdx === idx
                  ? "bg-indigo-600 text-white shadow-lg shadow-indigo-900/50"
                  : "bg-zinc-950 text-zinc-400 hover:text-white border border-zinc-800"
              }`}
            >
              <span>{scen.badge ? scen.badge.split(" ")[0] : "📌"}</span>
              <span className="truncate max-w-[170px]">{scen.title.split(":")[1] || scen.title}</span>
              <span className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${
                scen.evidence_fit_pct > 70 ? "bg-emerald-950 text-emerald-300 border border-emerald-800" : "bg-amber-950 text-amber-300 border border-amber-800"
              }`}>
                {scen.evidence_fit_pct}% Fit
              </span>
            </button>
          ))}
        </div>

        {/* Propose Custom Scenario Button */}
        <button
          onClick={() => setShowCustomModal(true)}
          className="px-3 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-semibold flex items-center gap-1.5 shadow transition active:scale-95"
        >
          <span>➕</span>
          <span>Propose Custom Scenario</span>
        </button>
      </div>

      {/* ----------------- TRANSPORT & TIMELINE CONTROLS HUD ----------------- */}
      <div className="px-4 py-2.5 bg-zinc-950 border-b border-zinc-800/80 flex flex-wrap items-center justify-between gap-3">
        {/* Digital Real-Time Clock & Action Status */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-zinc-900 border border-zinc-800 font-mono text-emerald-400 text-xs font-bold">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>{simState.clockStr}</span>
            <span className="text-[10px] text-zinc-500 ml-1">({Math.floor(simTime / 60)}m {Math.floor(simTime % 60)}s / 7m)</span>
          </div>
          <span className="text-xs text-zinc-200 font-semibold truncate max-w-md">
            {simState.phaseBadge}
          </span>
        </div>

        {/* Transport Buttons & Playback Speed */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setIsPlaying(false);
              setSimTime(0);
            }}
            className="p-1.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-300 text-xs"
            title="Start (02:18 AM)"
          >
            ⏮
          </button>
          <button
            onClick={() => {
              setSimTime((p) => Math.max(0, p - 15));
            }}
            className="p-1.5 px-2 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-300 text-xs font-bold"
            title="Step Back -15s"
          >
            ◀ -15s
          </button>
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className={`px-3.5 py-1.5 rounded font-bold text-xs flex items-center gap-1.5 shadow active:scale-95 ${
              isPlaying ? "bg-amber-600 hover:bg-amber-500 text-white" : "bg-emerald-600 hover:bg-emerald-500 text-white"
            }`}
          >
            {isPlaying ? "⏸ PAUSE" : "▶ PLAY"}
          </button>
          <button
            onClick={() => {
              setSimTime((p) => Math.min(420, p + 15));
            }}
            className="p-1.5 px-2 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-300 text-xs font-bold"
            title="Step Forward +15s"
          >
            +15s ▶
          </button>

          {/* Speed Selector */}
          <div className="ml-2 flex items-center border border-zinc-800 rounded bg-zinc-900 p-0.5 text-[10px]">
            {[1, 2, 5, 10].map((spd) => (
              <button
                key={spd}
                onClick={() => setPlaybackSpeed(spd)}
                className={`px-1.5 py-0.5 rounded font-semibold transition ${playbackSpeed === spd ? "bg-indigo-600 text-white" : "text-zinc-400 hover:text-white"}`}
              >
                {spd}x
              </button>
            ))}
          </div>

          {/* Collapsed 3-Perspective Viewpoint Dropdown */}
          <div className="ml-3 flex items-center gap-2">
            <div className="relative">
              <select
                value={cameraPreset}
                onChange={(e) => {
                  const k = e.target.value;
                  setCameraPreset(k);
                  setCameraFocusTarget(null);
                  if (k === "guard_sightline") setShowGuardSightline(true);
                }}
                className="bg-zinc-900 border border-zinc-700/80 hover:border-indigo-500 rounded-lg px-2.5 py-1 text-xs font-semibold text-zinc-100 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer shadow transition pr-7 appearance-none"
              >
                <option value="overview">🌐 Free 360° Orbit (Mouse & Touch)</option>
                <option value="cctv_alley">📹 CCTV-2 Alley Cam (Lens Angle)</option>
                <option value="guard_sightline">👁️ Guard Sightline POV (Witness Line-of-Sight)</option>
              </select>
              <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-zinc-400 text-[10px]">
                ▼
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ----------------- REAL-TIME TIMELINE SCRUBBER BAR ----------------- */}
      <div className="px-4 py-2 bg-zinc-900/90 border-b border-zinc-800 flex flex-col gap-1.5">
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={0}
            max={420}
            step={1}
            value={Math.round(simTime)}
            onChange={(e) => {
              setSimTime(parseFloat(e.target.value));
            }}
            className="w-full h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-emerald-500 hover:accent-emerald-400"
          />
        </div>
        {/* Forensic Action Milestone Markers */}
        <div className="flex justify-between text-[10px] text-zinc-400 font-mono overflow-x-auto gap-2">
          <button onClick={() => setSimTime(0)} className="hover:text-emerald-400 transition">02:18 Alley</button>
          <button onClick={() => setSimTime(65)} className="hover:text-emerald-400 transition">02:19 Pry Shutter</button>
          <button onClick={() => setSimTime(105)} className="hover:text-emerald-400 transition">02:20 Crawl Aperture</button>
          <button onClick={() => setSimTime(185)} className="hover:text-emerald-400 transition">02:21 Narcotics Vault & Bag</button>
          <button onClick={() => setSimTime(330)} className="hover:text-emerald-400 transition">02:23 Cash Till</button>
          <button onClick={() => setSimTime(390)} className="hover:text-emerald-400 transition">02:24 Egress Escape</button>
        </div>
      </div>

      {/* ----------------- 3D CANVAS + FORENSIC INSPECTOR HUD ----------------- */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-0 h-[520px]">
        {/* Interactive 3D Canvas with 100% Touch & Mouse Controls */}
        <div
          className="lg:col-span-2 relative bg-[#090d16] h-full cursor-grab active:cursor-grabbing select-none touch-none"
          style={{ touchAction: "none" }}
        >
          <Canvas camera={{ position: [12, 11, 12], fov: 46 }} style={{ width: "100%", height: "100%" }}>
            <SmoothCameraController
              preset={cameraPreset}
              focusTarget={cameraFocusTarget}
              manualZoom={manualZoomTrigger}
            />
            <RealisticRoomEnvironment
              simState={simState}
              onObjectClick={(obj) => {
                setInspectedObject(obj);
                if (obj.focusPos) setCameraFocusTarget(obj.focusPos);
              }}
              selectedObject={inspectedObject?.name || null}
              showGuardSightline={showGuardSightline}
            />
          </Canvas>

          {/* Top-Left: Click-to-inspect helper */}
          <div className="absolute top-3 left-3 flex items-center gap-2 z-10 pointer-events-none">
            <div className="bg-zinc-950/85 backdrop-blur border border-zinc-800 rounded-lg px-2.5 py-1 text-[10px] text-zinc-300 font-mono shadow flex items-center gap-1.5">
              <span className="text-amber-400">💡</span>
              <span>Click any 3D fixture to focus & inspect forensic evidence</span>
            </div>
          </div>

          {/* Bottom-Right: Interactive Zoom & Orbit Control Pad */}
          <div className="absolute bottom-3 right-3 flex items-center gap-1.5 z-20 bg-zinc-950/90 backdrop-blur border border-zinc-800 rounded-lg p-1 shadow-2xl">
            <button
              onClick={() => setManualZoomTrigger({ id: Date.now(), delta: 1 })}
              className="p-1.5 px-2.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-200 text-xs font-bold transition flex items-center gap-1.5 active:scale-95 border border-zinc-800/60"
              title="Zoom In (Scroll Up)"
            >
              <span className="text-sm font-extrabold">+</span>
              <span>Zoom In</span>
            </button>
            <button
              onClick={() => setManualZoomTrigger({ id: Date.now(), delta: -1 })}
              className="p-1.5 px-2.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-200 text-xs font-bold transition flex items-center gap-1.5 active:scale-95 border border-zinc-800/60"
              title="Zoom Out (Scroll Down)"
            >
              <span className="text-sm font-extrabold">-</span>
              <span>Zoom Out</span>
            </button>
            <button
              onClick={() => {
                setCameraPreset("overview");
                setCameraFocusTarget(null);
              }}
              className="p-1.5 px-2.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow active:scale-95"
              title="Reset 360° Orbit View"
            >
              <span>↻</span>
              <span>Reset 360°</span>
            </button>
          </div>

          {/* Bottom-Left: Interactive Controls Legend */}
          <div className="absolute bottom-3 left-3 hidden md:flex items-center gap-2 bg-zinc-950/90 backdrop-blur border border-zinc-800 rounded-lg px-3 py-1.5 text-[11px] text-zinc-300 font-mono shadow-2xl z-10 pointer-events-none">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-emerald-400 font-bold">100% Mouse & Touch:</span>
            <span>1-Finger / Left-Drag: Orbit 360°</span>
            <span className="text-zinc-600">|</span>
            <span>2-Finger / Scroll: Zoom</span>
            <span className="text-zinc-600">|</span>
            <span>Right-Drag: Pan</span>
          </div>
        </div>

        {/* Right Panel: Real-Time Forensic Narrative & Physics Verification */}
        <div className="p-4 bg-zinc-950/95 border-t lg:border-t-0 lg:border-l border-zinc-800 flex flex-col justify-between overflow-y-auto space-y-3">
          <div>
            {/* Clicked Object Forensic Inspector */}
            {inspectedObject ? (
              <div className="mb-3 p-3 bg-indigo-950/50 border border-indigo-700/80 rounded-lg shadow-lg">
                <div className="flex items-center justify-between text-xs font-bold text-indigo-300 mb-1">
                  <span>🔍 {inspectedObject.name}</span>
                  <button onClick={() => setInspectedObject(null)} className="text-zinc-500 hover:text-white">✕</button>
                </div>
                <div className="text-[10px] text-emerald-400 font-semibold mb-1">{inspectedObject.category}</div>
                <p className="text-xs text-zinc-300 leading-relaxed mb-2">{inspectedObject.description}</p>
                {inspectedObject.photoRef && (
                  <div className="mt-2 text-[10px] text-zinc-400 bg-zinc-900 border border-zinc-800 rounded p-1.5 flex items-center justify-between">
                    <span>Evidence Exhibit: {inspectedObject.photoRef}</span>
                    <span className="text-emerald-400 font-bold">Verified SAM 3.1</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="mb-3 p-3 bg-zinc-900/60 border border-zinc-800 rounded-lg">
                <div className="text-[11px] uppercase tracking-wider text-zinc-400 font-bold mb-1">
                  Forensic Scenario Hypothesis
                </div>
                <p className="text-xs text-zinc-200 leading-relaxed mb-2">
                  {currentScenario?.hypothesis_summary}
                </p>
                <div className="flex items-center justify-between text-[11px] pt-2 border-t border-zinc-800/60">
                  <span className="text-zinc-400">Evidence Fit:</span>
                  <span className="text-emerald-400 font-mono font-bold">{currentScenario?.evidence_fit_pct}% Plausible</span>
                </div>
              </div>
            )}

            {/* Live Forensic Narrative of Current Action */}
            <div className="p-3 bg-zinc-900/80 border border-zinc-800 rounded-lg space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase font-bold text-emerald-400">Real-Time Action Log</span>
                <span className="text-[10px] font-mono text-zinc-500">{simState.clockStr}</span>
              </div>
              <p className="text-xs text-zinc-300 leading-relaxed">
                {simState.narrative}
              </p>
              <div className="text-[10px] font-mono text-indigo-300 pt-1">
                Sensor: <span className="text-zinc-200">{simState.sensorStatus}</span>
              </div>
            </div>

            {/* Physics Kinematics Breakdown */}
            <div className="mt-3 p-3 bg-zinc-900/60 border border-zinc-800 rounded-lg space-y-2 text-xs">
              <div className="text-[11px] uppercase tracking-wider text-zinc-400 font-bold flex items-center justify-between">
                <span>Physics & Kinematics Check</span>
                <span className="text-emerald-400 font-mono">0 Wall Collisions</span>
              </div>

              <div className="space-y-1 text-[11px] text-zinc-300">
                <div className="flex justify-between">
                  <span className="text-zinc-500">Total Distance:</span>
                  <span className="font-mono text-zinc-200">27.2 m (Round-trip)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Transit Speed:</span>
                  <span className="font-mono text-zinc-200">Avg 0.06 m/s (Peak 1.4 m/s)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Aperture Clearance:</span>
                  <span className="font-mono text-emerald-400">PASS (0.95m vs 0.85m torso)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Guard Sightline:</span>
                  <span className="font-mono text-red-400">BLOCKED by Brick Pillar</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ----------------- OFFICER CUSTOM SCENARIO MODAL ----------------- */}
      {showCustomModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-6 max-w-lg w-full space-y-4 shadow-2xl">
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
              <div>
                <h3 className="text-base font-bold text-white">Investigative Hypothesis Sandbox</h3>
                <p className="text-xs text-zinc-400">Propose an alternative crime theory and test its physical validity.</p>
              </div>
              <button onClick={() => setShowCustomModal(false)} className="text-zinc-400 hover:text-white text-lg">✕</button>
            </div>

            {interviewQuestions.length === 0 ? (
              <div className="space-y-3">
                <label className="text-xs font-semibold text-zinc-300">
                  Officer's Scenario Hypothesis:
                </label>
                <textarea
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-xs text-white focus:outline-none focus:border-indigo-500"
                  rows={4}
                  placeholder="e.g. What if the intruder entered from the courtyard wall rather than the rear alley, hid until the guard changed shifts, and pried the shutter from the inside?"
                  value={customHypothesis}
                  onChange={(e) => setCustomHypothesis(e.target.value)}
                />
                <button
                  onClick={handleStartInterview}
                  disabled={interviewLoading || !customHypothesis.trim()}
                  className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition flex items-center justify-center gap-2"
                >
                  {interviewLoading ? "Consulting Forensic Advisor..." : "Verify Hypothesis with AI Advisor →"}
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="text-xs font-semibold text-emerald-400">
                  Forensic Advisor Verification Questions:
                </div>
                {interviewQuestions.map((q) => (
                  <div key={q.id} className="p-3 bg-zinc-900 border border-zinc-800 rounded space-y-1.5">
                    <div className="text-xs text-zinc-200 font-medium">{q.question}</div>
                    <div className="flex flex-wrap gap-1.5">
                      {q.suggested_answers?.map((ans: string, i: number) => (
                        <button
                          key={i}
                          onClick={() => setInterviewAnswers((prev) => ({ ...prev, [q.id]: ans }))}
                          className={`px-2 py-1 rounded text-[10px] transition ${
                            interviewAnswers[q.id] === ans
                              ? "bg-indigo-600 text-white font-bold"
                              : "bg-zinc-800 text-zinc-400 hover:text-white"
                          }`}
                        >
                          {ans}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}

                <button
                  onClick={handleSynthesizeScenario}
                  disabled={synthesizing}
                  className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition shadow-lg"
                >
                  {synthesizing ? "Synthesizing 3D Digital Twin..." : "Construct Custom Digital Twin & Simulate →"}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
