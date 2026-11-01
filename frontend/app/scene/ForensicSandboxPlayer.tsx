"use client";

import React, { useRef, useEffect, useState, useMemo } from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";

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

// Camera presets for close-up and tactical angles
const CAMERA_PRESETS: Record<string, { pos: [number, number, number]; target: [number, number, number]; label: string }> = {
  overview: { pos: [12, 11, 12], target: [0, 1, 0], label: "🌐 360° Free Orbit" },
  cctv_alley: { pos: [-5.8, 3.8, -7.5], target: [-4.5, 1.2, -5.5], label: "📹 CCTV-2 Alley Cam" },
  shutter_close: { pos: [-4.5, 1.5, -4.0], target: [-4.5, 1.0, -6.5], label: "🚪 Shutter Breach View" },
  vault_close: { pos: [2.0, 2.2, -2.5], target: [3.8, 1.0, -2.5], label: "🔒 Vault Interior" },
  counter_close: { pos: [0.8, 1.8, 3.8], target: [2.2, 0.9, 3.8], label: "💵 Cash Till View" },
  guard_sightline: { pos: [-8.5, 1.5, -5.5], target: [-4.5, 1.2, -6.85], label: "👁️ Guard Sightline POV" },
  suspect_pov: { pos: [-4.2, 1.7, -4.0], target: [-2.0, 1.2, -2.0], label: "🚶 Suspect POV" },
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

  // When camera preset changes
  useEffect(() => {
    const config = CAMERA_PRESETS[preset] || CAMERA_PRESETS["overview"];
    targetPos.current.set(...config.pos);
    targetLook.current.set(...config.target);
    isTransitioning.current = true;
  }, [preset]);

  // When user clicks a specific 3D object to focus
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

  // When user clicks on-screen Zoom In / Zoom Out buttons
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

    // Stop lerp once arrived within 5cm to yield 100% control to user mouse/touch
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
      onStart={() => {
        // Immediate user takeover on mouse rotate/pan/zoom
        isTransitioning.current = false;
      }}
    />
  );
}

/**
 * Photorealistic 3D Forensic Digital Twin Environment
 */
function RealisticRoomEnvironment({
  frame,
  onObjectClick,
  selectedObject,
  showGuardSightline,
}: {
  frame: any;
  onObjectClick: (obj: { name: string; category: string; description: string; photoRef?: string; focusPos?: [number, number, number] }) => void;
  selectedObject: string | null;
  showGuardSightline: boolean;
}) {
  const actorRef = useRef<THREE.Group>(null);
  const currentActorPos = useRef(new THREE.Vector3(-4.5, 0, -9));

  // Smooth suspect avatar gliding
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
  const sensorStatus = frame?.scene_state?.sensor_status ?? "Idle";

  return (
    <group>
      {/* Lighting: Realistic Multi-Point Forensic Illumination */}
      <ambientLight intensity={0.45} />
      <directionalLight position={[10, 18, 10]} intensity={0.8} castShadow />
      <pointLight position={[-4.5, 3.2, -6.0]} intensity={sensorStatus.includes("ALARM") ? 2.5 : 0.6} color={sensorStatus.includes("ALARM") ? "#ef4444" : "#f8fafc"} />
      <pointLight position={[3.8, 3.0, -2.5]} intensity={isVaultToppled ? 1.8 : 0.7} color={isVaultToppled ? "#f59e0b" : "#38bdf8"} />
      <pointLight position={[2.2, 2.5, 3.8]} intensity={isCounterOpen ? 1.8 : 0.6} color={isCounterOpen ? "#ef4444" : "#ffffff"} />

      {/* Concrete Warehouse Floor Plane */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]}>
        <planeGeometry args={[16, 20]} />
        <meshStandardMaterial color="#18181b" roughness={0.85} metalness={0.15} />
      </mesh>
      <gridHelper args={[24, 24, "#27272a", "#18181b"]} position={[0, 0.001, 0]} />

      {/* Architectural Cutaway Walls (Low Perimeter - No camera clipping) */}
      {/* Rear Brick Alley Wall */}
      <mesh position={[0, 1.6, -7.1]}>
        <boxGeometry args={[16, 3.2, 0.4]} />
        <meshStandardMaterial color="#3f3f46" roughness={0.9} />
      </mesh>
      {/* Left Wall Cutaway */}
      <mesh position={[-7.8, 1.0, 0]}>
        <boxGeometry args={[0.4, 2.0, 14]} />
        <meshStandardMaterial color="#27272a" transparent opacity={0.5} />
      </mesh>
      {/* Right Wall Cutaway */}
      <mesh position={[7.8, 1.0, 0]}>
        <boxGeometry args={[0.4, 2.0, 14]} />
        <meshStandardMaterial color="#27272a" transparent opacity={0.5} />
      </mesh>

      {/* -------------------- 1. GATE-B ROLLING SHUTTER (CLICKABLE) -------------------- */}
      <group
        position={[-4.5, 0, -6.9]}
        onClick={(e) => {
          e.stopPropagation();
          onObjectClick({
            name: "Gate-B Rolling Shutter",
            category: "Point of Forced Entry",
            description: "Corrugated steel rolling shutter. Pried from bottom center clasp with 18-inch crowbar. Lifted ~3.0 ft off concrete apron.",
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
          <meshStandardMaterial color="#71717a" metalness={0.8} roughness={0.3} />
        </mesh>
        <mesh position={[1.6, 1.6, 0]}>
          <boxGeometry args={[0.25, 3.2, 0.25]} />
          <meshStandardMaterial color="#71717a" metalness={0.8} roughness={0.3} />
        </mesh>
        {/* Housing Header Box */}
        <mesh position={[0, 3.25, 0]}>
          <boxGeometry args={[3.45, 0.35, 0.35]} />
          <meshStandardMaterial color="#52525b" metalness={0.7} />
        </mesh>

        {/* Dynamic Corrugated Slats (Moves smoothly upward) */}
        <mesh position={[0, 1.6 + shutterHeight / 2, 0]}>
          <boxGeometry args={[2.95, Math.max(0.1, 3.0 - shutterHeight), 0.08]} />
          <meshStandardMaterial
            color={selectedObject === "Gate-B Rolling Shutter" ? "#fbbf24" : shutterHeight > 0.2 ? "#ef4444" : "#a1a1aa"}
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

      {/* -------------------- 2. CCTV-ALLEY-02 CAMERA (CLICKABLE) -------------------- */}
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
        {/* Glass Lens */}
        <mesh position={[0, 0, 0.45]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.12, 0.12, 0.1, 16]} />
          <meshStandardMaterial color="#0284c7" emissive="#0284c7" emissiveIntensity={1.0} />
        </mesh>
      </group>

      {/* -------------------- 3. PHARMACY STORAGE RACKS & AISLE -------------------- */}
      <group position={[-2.2, 0, -2.0]}>
        {/* Industrial Metal Shelf Rack */}
        <mesh position={[0, 1.5, 0]}>
          <boxGeometry args={[0.7, 3.0, 4.0]} />
          <meshStandardMaterial color="#334155" wireframe />
        </mesh>
        {/* Shelf Planks */}
        {[-1.0, 0.0, 1.0].map((yOffset, i) => (
          <mesh key={i} position={[0, 1.5 + yOffset, 0]}>
            <boxGeometry args={[0.65, 0.05, 3.9]} />
            <meshStandardMaterial color="#475569" />
          </mesh>
        ))}
        {/* Stocked Medicine Cartons (Variety of Colors) */}
        <mesh position={[0, 0.8, -1.0]}>
          <boxGeometry args={[0.5, 0.45, 0.8]} />
          <meshStandardMaterial color="#0284c7" />
        </mesh>
        <mesh position={[0, 0.8, 0.5]}>
          <boxGeometry args={[0.45, 0.4, 0.9]} />
          <meshStandardMaterial color="#059669" />
        </mesh>
        <mesh position={[0, 1.8, -0.4]}>
          <boxGeometry args={[0.5, 0.5, 0.7]} />
          <meshStandardMaterial color="#d97706" />
        </mesh>
      </group>

      {/* -------------------- 4. HIGH-VALUE NARCOTICS VAULT (CLICKABLE) -------------------- */}
      <group
        position={[3.8, 0, -2.5]}
        onClick={(e) => {
          e.stopPropagation();
          onObjectClick({
            name: "High-Value Narcotics Vault",
            category: "Primary Target of Theft",
            description: "Glass-front lockable medicine cabinet. 120 units Alprazolam & Ketamine stolen. Cabinet pulled and toppled onto floor at 02:24 AM.",
            photoRef: "02_toppled_narcotics_cabinet.jpg",
            focusPos: [3.8, 1.0, -2.5],
          });
        }}
        onPointerOver={() => (document.body.style.cursor = "pointer")}
        onPointerOut={() => (document.body.style.cursor = "auto")}
      >
        {/* Steel Vault Cage Wireframe */}
        <mesh position={[0, 1.6, -1.8]}>
          <boxGeometry args={[3.2, 3.2, 0.1]} />
          <meshStandardMaterial color="#1e293b" transparent opacity={0.6} />
        </mesh>
        <mesh position={[-1.6, 1.6, 0]}>
          <boxGeometry args={[0.1, 3.2, 3.6]} />
          <meshStandardMaterial color="#1e293b" transparent opacity={0.6} />
        </mesh>

        {/* High-Value Medicine Cabinet (Tilts & Topples realistically!) */}
        <group
          position={[0.2, isVaultToppled ? 0.35 : 1.1, 0]}
          rotation={isVaultToppled ? [0, 0, Math.PI / 2.3] : [0, 0, 0]}
        >
          <mesh>
            <boxGeometry args={[0.85, 2.2, 1.5]} />
            <meshStandardMaterial
              color={selectedObject === "High-Value Narcotics Vault" ? "#fbbf24" : isVaultToppled ? "#f59e0b" : "#f1f5f9"}
              metalness={0.5}
              roughness={0.25}
            />
          </mesh>
          {/* Shattered / Open Glass Door */}
          <mesh position={[0.44, 0, 0]}>
            <boxGeometry args={[0.02, 2.0, 1.3]} />
            <meshStandardMaterial color="#38bdf8" transparent opacity={0.4} />
          </mesh>
        </group>
      </group>

      {/* -------------------- 5. FRONT BILLING COUNTER & TILL (CLICKABLE) -------------------- */}
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
        {/* Wooden Counter L-Desk */}
        <mesh position={[0, 0.55, 0]}>
          <boxGeometry args={[3.0, 1.1, 1.2]} />
          <meshStandardMaterial
            color={selectedObject === "Front Billing Counter & Till" ? "#fbbf24" : "#78350f"}
            roughness={0.7}
          />
        </mesh>
        {/* Computer Screen / POS Display */}
        <mesh position={[-0.8, 1.35, 0]}>
          <boxGeometry args={[0.1, 0.45, 0.65]} />
          <meshStandardMaterial color="#0f172a" />
        </mesh>
        {/* Sliding Cash Register Till */}
        <mesh position={[0.6, 0.9, isCounterOpen ? 0.85 : 0.45]}>
          <boxGeometry args={[0.8, 0.22, 0.6]} />
          <meshStandardMaterial color={isCounterOpen ? "#ef4444" : "#475569"} metalness={0.6} />
        </mesh>
      </group>

      {/* -------------------- 6. EVIDENCE MARKER #1 (CROWBAR & GLOVE) -------------------- */}
      <group
        position={[1.6, 0, 2.6]}
        onClick={(e) => {
          e.stopPropagation();
          onObjectClick({
            name: "Evidence Marker #1",
            category: "Physical Evidence Exhibit",
            description: "18-inch rusted iron crowbar with blue paint scrapings, and a single blue nitrile surgical glove discarded on concrete floor.",
            photoRef: "03_discarded_crowbar_and_glove.jpg",
            focusPos: [-1.2, 0.1, -4.8],
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
        {/* Discarded Iron Crowbar on Floor */}
        <mesh position={[0.4, 0.03, -0.2]} rotation={[0, 0.5, 0]}>
          <boxGeometry args={[0.06, 0.04, 0.85]} />
          <meshStandardMaterial color="#78716c" metalness={0.8} />
        </mesh>
        {/* Blue Nitrile Glove on Floor */}
        <mesh position={[0.3, 0.02, 0.2]}>
          <boxGeometry args={[0.2, 0.02, 0.25]} />
          <meshStandardMaterial color="#2563eb" roughness={0.9} />
        </mesh>
      </group>

      {/* -------------------- 7. NIGHT GUARD BOOTH & SIGHTLINE CONE -------------------- */}
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
        {/* Guard Booth Shelter */}
        <mesh position={[0, 1.2, 0]}>
          <boxGeometry args={[1.5, 2.4, 1.5]} />
          <meshStandardMaterial color="#1e293b" transparent opacity={0.7} />
        </mesh>
        {/* Visual Sightline Raycast Cone */}
        {showGuardSightline && (
          <mesh position={[2.0, 1.2, -0.6]} rotation={[0, -0.3, 0]}>
            <coneGeometry args={[1.2, 4.5, 16]} />
            <meshBasicMaterial color="#ef4444" transparent opacity={0.25} />
          </mesh>
        )}
      </group>

      {/* -------------------- 8. 3D SUSPECT AVATAR (NO CLIPPING) -------------------- */}
      {frame?.actor?.visible && (
        <group
          ref={actorRef}
          position={frame.actor.pos}
          onClick={(e) => {
            e.stopPropagation();
            onObjectClick({
              name: "Suspect Silhouette",
              category: "Reconstructed Actor",
              description: "Male, approx 5'9\", dark hooded rain jacket, white sports shoes. Modeled with physical clearance from all fixtures.",
            });
          }}
        >
          {/* Soft Ground Shadow Disc */}
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
            <circleGeometry args={[0.45, 32]} />
            <meshBasicMaterial color="#000000" transparent opacity={0.6} />
          </mesh>

          {/* Torso: Dark Hooded Jacket */}
          <mesh position={[0, 1.1, 0]}>
            <capsuleGeometry args={[0.26, 0.75, 8, 16]} />
            <meshStandardMaterial color="#09090b" roughness={0.5} />
          </mesh>

          {/* Head & Hood */}
          <mesh position={[0, 1.7, 0]}>
            <sphereGeometry args={[0.22, 16, 16]} />
            <meshStandardMaterial color="#18181b" roughness={0.6} />
          </mesh>

          {/* Legs */}
          <mesh position={[-0.12, 0.45, 0]}>
            <cylinderGeometry args={[0.08, 0.08, 0.7, 8]} />
            <meshStandardMaterial color="#09090b" />
          </mesh>
          <mesh position={[0.12, 0.45, 0]}>
            <cylinderGeometry args={[0.08, 0.08, 0.7, 8]} />
            <meshStandardMaterial color="#09090b" />
          </mesh>

          {/* White Sports Shoes */}
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
  const [currentFrameIdx, setCurrentFrameIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
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

  const currentScenario = scenarios[activeScenarioIdx] || scenarios[0];
  const frames = currentScenario?.frames || [];
  const currentFrame = frames[currentFrameIdx] || frames[0];

  // Playback timer
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
  }, [isPlaying, playbackSpeed, frames.length]);

  // Handle Scenario Switch
  const handleSelectScenario = (idx: number) => {
    setActiveScenarioIdx(idx);
    setCurrentFrameIdx(0);
    setIsPlaying(false);
    setInspectedObject(null);
    setCameraFocusTarget(null);
  };

  // Step 1: Submit hypothesis to generate Socratic Interview
  const handleStartInterview = async () => {
    if (!customHypothesis.trim()) return;
    setInterviewLoading(true);
    try {
      const res = await fetch(`http://127.0.0.1:8010/cases/${caseId}/sandbox/custom-scenario/interview`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("cw_token")}`,
        },
        body: JSON.stringify({ hypothesis_text: customHypothesis }),
      });
      const data = await res.json();
      setInterviewQuestions(data.questions || []);
    } catch (e) {
      console.error("Interview generation failed:", e);
    } finally {
      setInterviewLoading(false);
    }
  };

  // Step 2: Submit interview answers to synthesize custom scenario
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
    <div className="flex flex-col border border-zinc-800 rounded-xl bg-zinc-950 overflow-hidden shadow-2xl">
      {/* ----------------- TOP SCENARIO HYPOTHESIS SELECTOR ----------------- */}
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
              <span>{scen.badge.split(" ")[0]}</span>
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
          className="px-3 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-semibold flex items-center gap-1.5 shadow transition"
        >
          <span>➕</span>
          <span>Propose Custom Scenario</span>
        </button>
      </div>

      {/* ----------------- TRANSPORT & CAMERA CONTROLS HUD ----------------- */}
      <div className="px-4 py-2.5 bg-zinc-950 border-b border-zinc-800/80 flex flex-wrap items-center justify-between gap-3">
        {/* Digital Clock & Frame Info */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-zinc-900 border border-zinc-800 font-mono text-emerald-400 text-xs font-bold">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>{currentFrame?.timestamp}</span>
          </div>
          <span className="text-xs text-zinc-300 font-medium truncate max-w-sm">
            {currentFrame?.title}
          </span>
        </div>

        {/* Transport Controls */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => {
              setIsPlaying(false);
              setCurrentFrameIdx(0);
            }}
            className="p-1.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-300 text-xs"
            title="Start"
          >
            ⏮
          </button>
          <button
            onClick={() => {
              setIsPlaying(false);
              setCurrentFrameIdx((p) => Math.max(0, p - 1));
            }}
            className="p-1.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-300 text-xs"
            title="Previous"
          >
            ◀
          </button>
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className={`px-3 py-1.5 rounded font-bold text-xs flex items-center gap-1.5 ${
              isPlaying ? "bg-amber-600 text-white" : "bg-emerald-600 text-white shadow"
            }`}
          >
            {isPlaying ? "⏸ PAUSE" : "▶ PLAY"}
          </button>
          <button
            onClick={() => {
              setIsPlaying(false);
              setCurrentFrameIdx((p) => Math.min(frames.length - 1, p + 1));
            }}
            className="p-1.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-300 text-xs"
            title="Next"
          >
            ▶
          </button>

          {/* Speed Toggle */}
          <div className="ml-2 flex items-center border border-zinc-800 rounded bg-zinc-900 p-0.5 text-[10px]">
            {[1, 2, 5].map((spd) => (
              <button
                key={spd}
                onClick={() => setPlaybackSpeed(spd)}
                className={`px-1.5 py-0.5 rounded ${playbackSpeed === spd ? "bg-indigo-600 text-white" : "text-zinc-400"}`}
              >
                {spd}x
              </button>
            ))}
          </div>
        </div>

        {/* Camera Angles Toolbar */}
        <div className="flex items-center gap-1">
          {Object.entries(CAMERA_PRESETS).map(([k, v]) => (
            <button
              key={k}
              onClick={() => {
                setCameraPreset(k);
                if (k === "guard_sightline") setShowGuardSightline(true);
              }}
              className={`px-2 py-1 rounded text-[10px] font-medium transition ${
                cameraPreset === k ? "bg-indigo-600 text-white shadow" : "bg-zinc-900 text-zinc-400 hover:text-white"
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {/* ----------------- 3D CANVAS + TACTICAL INSPECTION HUD ----------------- */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-0 h-[520px]">
        {/* Interactive 3D Canvas */}
        <div className="lg:col-span-2 relative bg-[#090a0f] h-full cursor-grab active:cursor-grabbing select-none">
          <Canvas camera={{ position: [12, 11, 12], fov: 46 }} style={{ width: "100%", height: "100%" }}>
            <SmoothCameraController
              preset={cameraPreset}
              focusTarget={cameraFocusTarget}
              manualZoom={manualZoomTrigger}
            />
            <RealisticRoomEnvironment
              frame={currentFrame}
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
              <span>Click any object in 3D to focus & inspect forensic exhibit</span>
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
            <span className="text-emerald-400 font-bold">Interactive:</span>
            <span>Left-Drag: Rotate 360°</span>
            <span className="text-zinc-600">|</span>
            <span>Right-Drag: Pan</span>
            <span className="text-zinc-600">|</span>
            <span>Scroll: Zoom In/Out</span>
          </div>

          {/* Conflict Warning Flare */}
          {currentFrame?.conflict_banner && (
            <div className="absolute bottom-3 left-3 right-3 bg-red-950/90 backdrop-blur border border-red-700/80 rounded p-2 text-xs text-red-200 shadow-xl flex items-center justify-between">
              <span>{currentFrame.conflict_banner}</span>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-red-900 text-red-100">
                Uncalibrated DVR
              </span>
            </div>
          )}
        </div>

        {/* Right Panel: Physics Validation & Forensic Inspector Card */}
        <div className="p-4 bg-zinc-950/95 border-t lg:border-t-0 lg:border-l border-zinc-800 flex flex-col justify-between overflow-y-auto space-y-3">
          <div>
            {/* Clicked Object Forensic Inspector */}
            {inspectedObject ? (
              <div className="mb-3 p-3 bg-indigo-950/50 border border-indigo-700/80 rounded-lg shadow-lg">
                <div className="flex items-center justify-between text-xs font-bold text-indigo-300 mb-1">
                  <span>🔍 {inspectedObject.name}</span>
                  <button onClick={() => setInspectedObject(null)} className="text-zinc-500 hover:text-white">✕</button>
                </div>
                <div className="text-[10px] text-indigo-400 uppercase font-mono mb-1">{inspectedObject.category}</div>
                <p className="text-xs text-zinc-200 leading-tight mb-2">{inspectedObject.description}</p>
                {inspectedObject.photoRef && (
                  <div className="text-[10px] font-mono text-emerald-400 bg-zinc-900 p-1.5 rounded flex items-center justify-between">
                    <span>📷 Exhibit: {inspectedObject.photoRef}</span>
                    <span className="underline">View SAM 3.1</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="mb-3 p-2.5 bg-zinc-900/60 border border-zinc-800 rounded text-xs text-zinc-400">
                <span className="font-semibold text-zinc-300">Hypothesis Summary:</span> {currentScenario.hypothesis_summary}
              </div>
            )}

            {/* REAL-WORLD PHYSICS & KINEMATICS VALIDATION */}
            <div className="p-3 bg-zinc-900/80 border border-zinc-800 rounded-lg space-y-2">
              <div className="flex items-center justify-between text-xs font-bold">
                <span className="text-zinc-300">⚖️ Physics & Real-World Validation</span>
                <span className={`text-[10px] px-2 py-0.5 rounded font-mono ${
                  currentScenario.physics_validation.is_physically_possible ? "bg-emerald-950 text-emerald-400 border border-emerald-800" : "bg-red-950 text-red-400 border border-red-800"
                }`}>
                  {currentScenario.physics_validation.is_physically_possible ? "PHYSICALLY VALID" : "CONTRADICTED"}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
                <div className="p-1.5 bg-zinc-950 rounded border border-zinc-800">
                  <div className="text-[9px] text-zinc-500">TRANSIT DISTANCE</div>
                  <div className="text-zinc-200 font-bold">{currentScenario.physics_validation.total_distance_meters} m</div>
                </div>
                <div className="p-1.5 bg-zinc-950 rounded border border-zinc-800">
                  <div className="text-[9px] text-zinc-500">MAX TRANSIT SPEED</div>
                  <div className="text-zinc-200 font-bold">{currentScenario.physics_validation.max_speed_mps} m/s</div>
                </div>
              </div>

              {/* Clearance & Line-of-sight checks */}
              <div className="text-[10px] space-y-1 pt-1 border-t border-zinc-800/80 text-zinc-400">
                <div>✓ {currentScenario.physics_validation.clearance_check}</div>
                <div>👁️ Sightline: <span className="text-zinc-300">{currentScenario.physics_validation.line_of_sight.explanation}</span></div>
              </div>
            </div>

            {/* Supporting Facts vs Contradictions */}
            <div className="mt-3 space-y-2 text-xs">
              <div className="p-2 bg-emerald-950/20 border border-emerald-900/50 rounded">
                <div className="text-[10px] font-bold text-emerald-400 uppercase mb-1">Supporting Forensic Facts</div>
                <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-zinc-300">
                  {currentScenario.supporting_facts.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>

              {currentScenario.contradicted_points.length > 0 && (
                <div className="p-2 bg-red-950/20 border border-red-900/50 rounded">
                  <div className="text-[10px] font-bold text-red-400 uppercase mb-1">Forensic Discrepancies</div>
                  <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-red-200/90">
                    {currentScenario.contradicted_points.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ----------------- OFFICER CUSTOM SCENARIO BUILDER MODAL ----------------- */}
      {showCustomModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-6 max-w-xl w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div>
                <h3 className="text-base font-bold text-white">Investigative Hypothesis Sandbox</h3>
                <p className="text-xs text-zinc-400">Propose an alternative crime theory and test its physical validity.</p>
              </div>
              <button onClick={() => setShowCustomModal(false)} className="text-zinc-500 hover:text-white">✕</button>
            </div>

            {/* Step 1: Propose Theory */}
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
              /* Step 2: Socratic Forensic Interview */
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
