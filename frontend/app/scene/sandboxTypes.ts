// Types mirroring backend/pipeline/sandbox*.py (schema 3).
// Everything the screen shows comes from these fields; nothing is tied to one case.

export type Vec3 = [number, number, number];
export type Basis = "stated" | "inferred" | "assumed" | "officer";
export type OpeningState = "forced" | "intact" | "locked" | "open" | "unknown";

interface NodeBase {
  id: string;
  label: string;
  evidence_refs: string[];
  basis: Basis;
  reachable: boolean;
  stand_pos: Vec3;
  face_pos: Vec3 | null;
}

export interface Room extends NodeBase {
  level: number;
  height_m: number;
  rect: [number, number, number, number]; // x0, x1, z0, z1 along wall centre-lines
  width_m: number;
  length_m: number;
  floor_y: number;
  observed: boolean;
  dimensions_basis: "stated" | "inferred" | "assumed" | "measured";
  placement_note?: string;
  pos: Vec3;
}

export interface Opening extends NodeBase {
  kind: "door" | "stairs" | "external";
  room_a: string;
  room_b: string | null;
  wall: "north" | "south" | "east" | "west" | null;
  orient: "x" | "z" | null;
  line: number;
  level: number;
  gap_center_m: number;
  width_m: number;
  state: OpeningState;
  state_note: string;
  passable: boolean;
  gap_pos: Vec3;
  pos_a: Vec3;
  pos_b: Vec3 | null;
  outside_pos: Vec3 | null;
  vertical_m?: number;
  position_frac: number | [number, number];
}

export interface Fixture extends NodeBase {
  room: string;
  category: string;
  pos: Vec3;
  footprint_m: [number, number];
  height_m: number;
  color_hex: string;
  position_frac: [number, number];
  adjusted: boolean;
  adjust_notes: string[];
  requested_pos: Vec3;
}

export interface KeyLocation extends NodeBase {
  room: string;
  pos: Vec3;
  significance: string;
  on_fixture: string | null;
}

export interface OutdoorObject extends NodeBase {
  room: "outside";
  kind: string;
  pos: Vec3;
  footprint_m: [number, number];
  height_m: number;
  color_hex: string;
}

export interface Observer extends NodeBase {
  kind: "camera" | "witness";
  room: string;
  level: number;
  pos: Vec3;
  eye_height_m: number;
  fov_deg: number;
  range_m: number;
  yaw: number;
}

export interface Layout {
  schema_version: number;
  engine_version: string;
  wall_thickness_m: number;
  actor_radius_m: number;
  door_height_m: number;
  dimensions_basis: string;
  rooms: Room[];
  levels: { level: number; floor_y: number; height_m: number }[];
  openings: Opening[];
  fixtures: Fixture[];
  key_locations: KeyLocation[];
  outdoor_objects: OutdoorObject[];
  observers: Observer[];
  notes: string;
  warnings: string[];
  defaults_used: string[];
  limits: string[];
  coverage: { stated: number; inferred: number; assumed: number; officer: number };
  scene_assessment?: { physical_scene_supported: boolean; reason: string };
  source?: Record<string, unknown>;
}

export interface Segment {
  kind: "transit" | "dwell";
  actor: string;
  t0: number;
  t1: number;
  step: number;
  node_id: string;
  label: string;
  action: string;
  phase: string;
  narrative: string;
  route?: Vec3[];
  leg_kinds?: string[];
  leg_factors?: number[];
  leg_lengths?: number[];
  length_m?: number;
  eff_length_m?: number;
  v_max?: number;
  accel?: number;
  pos?: Vec3;
  face_pos: Vec3 | null;
  auto_routed: boolean;
  routing_notes: string[];
  carrying: boolean;
  item: string;
  evidence_refs: string[];
  failed: boolean;
  space: string;
}

export interface PlanStep {
  k: number;
  actor: string;
  node_id: string;
  label: string;
  action: string;
  phase: string;
  narrative: string;
  evidence_refs: string[];
  strong_refs?: string[];
  weak_refs?: string[];
  basis: string;
  claimed_s: number;
  arrive_s: number;
  depart_s: number;
  route_notes: string[];
  auto_routed: boolean;
  item: string;
  effects: { target: string; state: string }[];
  observed_by: string[];
}

export interface PlanActor {
  id: string;
  label: string;
  role: string;
  color: string;
  start_offset_s: number;
  end_s: number;
  evidence_refs: string[];
  segments: Segment[];
  steps: PlanStep[];
}

export interface Fact {
  text: string;
  refs: string[];
  invalid_refs: string[];
  weak_refs?: string[];
  supported: boolean;
}

export interface Violation {
  code: string;
  step: number | null;
  actor?: string | null;
  message: string;
}

export interface EvidenceEntry {
  id: string;
  kind: "observation" | "entity" | "evidence";
  text: string;
  time?: string | null;
  classification?: string | null;
  filename?: string | null;
  locator?: string | null;
  limitations?: string | null;
}

export interface TimeAnchor {
  actor: string;
  actor_label: string;
  step: number;
  t_model: number;
  sod: number;
  observation_id: string;
  label: string;
  clock_text: string;
}

export interface Scenario {
  scenario_id: string;
  run_id: string;
  scenario_type: "automated" | "officer_custom";
  status: "active" | "retracted";
  rank: number | null;
  title: string;
  hypothesis_summary: string;
  plausibility_estimate: number;
  score: {
    verifiable_score: number;
    llm_estimate: number;
    cap_reason: string | null;
    formula: string;
    components: Record<string, number | Record<string, number>>;
  };
  supporting_facts: Fact[];
  contradicted_points: Fact[];
  actors: { id: string; label: string; role: string; color: string; start_offset_s: number; end_s: number; evidence_refs: string[] }[];
  plan: {
    actors: PlanActor[];
    dropped_steps: { index: number; node_id: string; reason: string }[];
    route_notes: string[];
    doors_used: { id: string; label: string; state: OpeningState; first_step: number; actor: string; chosen_by_system: boolean }[];
    effects: { t: number; target: string; state: string; actor: string; step: number; cited: boolean }[];
    total_duration_s: number;
    total_distance_m: number;
    time_adjustments: { step: number; actor?: string; claimed_s: number; modelled_s: number; reason: string }[];
  };
  validation: {
    is_physically_possible: boolean;
    violations: Violation[];
    warnings: string[];
    checks_run: string[];
    checks_not_run: string[];
    observation_checks: { actor: string; step: number; observer: string; visible: boolean; reason: string; label: string }[];
    total_distance_m: number;
    total_duration_s: number;
    max_modelled_speed_mps: number;
  };
  time: {
    anchors: TimeAnchor[];
    unmodelled_gaps: { message: string }[];
    cross_source_notes: string[];
    cross_person_notes: string[];
    basis: "anchored" | "officer" | "none";
    note: string;
    clock_anchors: { t_model: number; sod: number; observation_id: string; actor: string }[];
  };
  weak_citations: { actor: string; step: number | null; ref: string }[];
  unsupported_time_mentions: string[];
  disputed_citations: string[];
  citations_removed: number;
  narrative_consistency: { available: boolean; note?: string; facts_total?: number; facts_not_reflected?: string[] };
  evidence_index: Record<string, EvidenceEntry>;
  provenance: { provider: string; model: string; prompt_hash: string; layout_hash: string; engine_version?: string; redacted?: boolean; replanned_from?: string };
  created_at: string;
  content_hash?: string;
  engine_version?: string;
  revalidated_with?: string;
  revalidation_note?: string;
  retracted?: { by: string; at: string; reason: string };
  officer_input?: { hypothesis: string; interview: { question: string; answer: string }[]; submitted_by: string; times_mentioned?: string[] };
}

export interface RunInfo {
  run_id: string;
  status: string;
  is_current: boolean;
  mode: string;
  schema_version: number;
  layout_hash: string | null;
  evidence_hash: string | null;
  approved_by: string | null;
  approved_at: string | null;
  created_by: string | null;
  created_at: string;
  completed_at: string | null;
  status_message: string | null;
  layout?: Layout | null;
  assessment?: { physical_scene_supported?: boolean; reason?: string };
  evidence_index?: Record<string, EvidenceEntry>;
  generation?: {
    calls?: { step: string; provider: string; model: string; prompt_hash: string; seconds: number; redacted?: boolean }[];
    evidence?: { observations_total: number; observations_shown: number; observations_omitted: number; timed_observations: number; evidence_files: number };
    redaction?: { enabled: boolean; replacements: Record<string, number>; not_covered: string[] };
    vision_cues?: { enabled: boolean; images_sent: number };
    layout_reused_from?: string;
    edited_from?: string;
  };
}

export interface SandboxState {
  status: "none" | "generating" | "ready" | "failed" | "insufficient_evidence" | "outdated";
  generating: { run_id: string; started_at: string } | null;
  last_failure: { run_id: string; message: string; at: string } | null;
  run: RunInfo | null;
  scenarios: Scenario[];
  scenarios_on_other_layouts: { scenario_id: string; run_id: string; title: string; created_at: string }[];
  stale: boolean;
  stale_detail: string;
  history: { run_id: string; status: string; mode: string; created_at: string; created_by: string | null; is_current: boolean; schema_version: number }[];
  disclaimer: string;
  score_formula: string;
  engine_version: string;
  redaction_default: boolean;
}

export interface InspectedItem {
  id?: string;
  nodeKind?: "room" | "opening" | "fixture" | "key_location" | "observer" | "outdoor_object" | "wall" | "route";
  title: string;
  kind: string;
  basis?: Basis | "derived";
  description: string;
  refs?: string[];
  notes?: string[];
  focus?: Vec3;
}

export type EditOp = { op: "set" | "add" | "remove"; kind: string; id?: string; fields?: Record<string, unknown> };
