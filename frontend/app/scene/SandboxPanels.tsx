"use client";

import React, { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { Basis, EditOp, EvidenceEntry, InspectedItem, Layout, PhotoLinks, SandboxReview, Scenario } from "./sandboxTypes";

export const BASIS_STYLE: Record<Basis | "derived", string> = {
  stated: "bg-emerald-950 text-emerald-300 border-emerald-800",
  inferred: "bg-sky-950 text-sky-300 border-sky-800",
  assumed: "bg-rose-950 text-rose-300 border-rose-800",
  officer: "bg-violet-950 text-violet-300 border-violet-800",
  derived: "bg-zinc-900 text-zinc-300 border-zinc-700",
};
const BASIS_HELP: Record<Basis | "derived", string> = {
  stated: "Stated in the evidence",
  inferred: "Reasoned from evidence, not stated",
  assumed: "A guess: no evidence behind it",
  officer: "Entered or corrected by an officer",
  derived: "Computed by the system",
};

export function BasisBadge({ basis }: { basis: Basis | "derived" }) {
  return (
    <span title={BASIS_HELP[basis]} className={`px-1.5 py-0.5 rounded border text-[10px] uppercase tracking-wide ${BASIS_STYLE[basis]}`}>
      {basis}
    </span>
  );
}

export function RefChips({ refs, index }: { refs: string[]; index: Record<string, EvidenceEntry> }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!refs.length) return <span className="text-[10px] text-zinc-500 italic">no evidence cited</span>;
  const entry = open ? index[open] : undefined;
  return (
    <div>
      <div className="flex flex-wrap gap-1">
        {refs.map((r) => (
          <button
            key={r}
            onClick={() => setOpen(open === r ? null : r)}
            className={`px-1.5 py-0.5 rounded border text-[10px] font-mono ${open === r ? "bg-indigo-900 border-indigo-600 text-indigo-100" : "bg-zinc-900 border-zinc-700 text-zinc-300 hover:border-zinc-500"}`}
          >
            {r}
          </button>
        ))}
      </div>
      {open && (
        <div className="mt-1.5 p-2 rounded border border-zinc-700 bg-zinc-950 text-[11px] text-zinc-300 space-y-0.5">
          {entry ? (
            <>
              <div>{entry.text}</div>
              <div className="text-zinc-500">
                {entry.kind}
                {entry.time ? ` · recorded time ${entry.time}` : ""}
                {entry.filename ? ` · ${entry.filename}` : ""}
                {entry.locator ? ` · ${entry.locator}` : ""}
              </div>
              {entry.limitations && <div className="text-amber-400">Limitation: {entry.limitations}</div>}
            </>
          ) : (
            <div className="text-zinc-500">Source text not stored for this id.</div>
          )}
        </div>
      )}
    </div>
  );
}

export function Section({ title, children, tone = "default" }: { title: string; children: React.ReactNode; tone?: "default" | "good" | "bad" | "warn" }) {
  const color = { default: "text-zinc-400", good: "text-emerald-400", bad: "text-red-400", warn: "text-amber-400" }[tone];
  return (
    <div className="p-3 bg-zinc-900/60 border border-zinc-800 rounded-lg space-y-1.5">
      <div className={`text-[10px] uppercase tracking-wider font-bold ${color}`}>{title}</div>
      {children}
    </div>
  );
}

/** A broken 3D view (for example no WebGL) must not take the rest of the page down. */
export class SceneBoundary extends React.Component<{ children: React.ReactNode; resetKey: string }, { failed: string | null; key: string }> {
  state = { failed: null as string | null, key: this.props.resetKey };
  static getDerivedStateFromError(e: unknown) {
    return { failed: e instanceof Error ? e.message : "unknown error" };
  }
  static getDerivedStateFromProps(p: { resetKey: string }, s: { key: string }) {
    return p.resetKey !== s.key ? { failed: null, key: p.resetKey } : null;
  }
  render() {
    if (this.state.failed) {
      return (
        <div className="h-full flex flex-col items-center justify-center gap-2 text-center p-6 text-xs text-zinc-400">
          <div className="text-amber-300">The 3D view could not be drawn ({this.state.failed}).</div>
          <div>The checks, steps and evidence on the right are still correct. Try another browser or enable hardware acceleration.</div>
          <button className="underline" onClick={() => this.setState({ failed: null })}>Try again</button>
        </div>
      );
    }
    return this.props.children;
  }
}

// ---------------------------------------------------------------- comparison matrix

export function ComparisonMatrix({ scenarios, activeId, onPick, overlay, setOverlay }: {
  scenarios: Scenario[];
  activeId: string | undefined;
  onPick: (id: string) => void;
  overlay: boolean;
  setOverlay: (v: boolean) => void;
}) {
  if (scenarios.length < 2) return null;
  const rows: [string, (s: Scenario) => React.ReactNode][] = [
    ["Reading", (s) => (s.support_level === "less_supported" ? <span className="text-amber-300">less supported possibility</span> : s.support_level === "alternative" ? <span className="text-sky-300">alternative reading</span> : <span className="text-emerald-300">best supported</span>)],
    ["Differs by", (s) => <span className="text-zinc-400 whitespace-normal">{s.differs_by || "—"}</span>],
    ["Evidence score", (s) => <span className="font-mono">{s.score.verifiable_score}</span>],
    ["Physically consistent", (s) => (s.validation.is_physically_possible ? <span className="text-emerald-400">yes</span> : <span className="text-red-400">{s.validation.violations.length} problem(s)</span>)],
    ["People", (s) => s.plan.actors.length],
    ["Duration", (s) => `${Math.round(s.plan.total_duration_s)} s`],
    ["Distance", (s) => `${s.plan.total_distance_m.toFixed(1)} m`],
    ["Steps citing evidence", (s) => `${s.score.components.steps_citing_evidence}/${s.score.components.steps_total}`],
    ["Points against", (s) => String(s.score.components.contradictions)],
    ["Cautions", (s) => String(s.validation.warnings.length + s.weak_citations.length + s.unsupported_time_mentions.length + s.disputed_citations.length)],
  ];
  return (
    <Section title="Compare scenarios">
      <div className="overflow-x-auto">
        <table className="w-full text-[10px] text-zinc-300">
          <thead>
            <tr>
              <th className="text-left text-zinc-500 font-normal pr-2" />
              {scenarios.map((s) => (
                <th key={s.scenario_id} className="text-left pr-2">
                  <button onClick={() => onPick(s.scenario_id)} className={`underline ${s.scenario_id === activeId ? "text-indigo-300" : "text-zinc-300"}`}>
                    {s.scenario_type === "officer_custom" ? "Officer" : `#${s.rank}`}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, fn]) => (
              <tr key={name} className="border-t border-zinc-800">
                <td className="text-zinc-500 pr-2 py-0.5">{name}</td>
                {scenarios.map((s) => <td key={s.scenario_id} className="pr-2 py-0.5">{fn(s)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <label className="flex items-center gap-1 text-[11px] text-zinc-400">
        <input type="checkbox" checked={overlay} onChange={(e) => setOverlay(e.target.checked)} /> Draw the other scenarios&apos; routes in the 3D view
      </label>
    </Section>
  );
}

// ---------------------------------------------------------------- officer editor

type FieldDef = { key: string; label: string; type: "text" | "number" | "select"; options?: string[] };

const FIELDS: Record<string, FieldDef[]> = {
  room: [
    { key: "label", label: "Name", type: "text" },
    { key: "width_m", label: "Width (m)", type: "number" },
    { key: "length_m", label: "Length (m)", type: "number" },
    { key: "height_m", label: "Ceiling height (m)", type: "number" },
  ],
  fixture: [
    { key: "label", label: "Name", type: "text" },
    { key: "category", label: "Category", type: "text" },
    { key: "height_m", label: "Height (m)", type: "number" },
  ],
  opening: [
    { key: "label", label: "Name", type: "text" },
    { key: "state", label: "State", type: "select", options: ["unknown", "open", "intact", "locked", "forced"] },
    { key: "state_note", label: "Note", type: "text" },
    { key: "width_m", label: "Width (m)", type: "number" },
  ],
  key_location: [
    { key: "label", label: "Name", type: "text" },
    { key: "significance", label: "Why it matters", type: "text" },
  ],
  observer: [
    { key: "label", label: "Name", type: "text" },
    { key: "fov_deg", label: "Field of view (deg)", type: "number" },
    { key: "range_m", label: "Range (m)", type: "number" },
  ],
  outdoor_object: [
    { key: "label", label: "Name", type: "text" },
    { key: "height_m", label: "Height (m)", type: "number" },
  ],
};

const COLLECTION: Record<string, keyof Layout> = {
  room: "rooms", fixture: "fixtures", opening: "openings", key_location: "key_locations", observer: "observers", outdoor_object: "outdoor_objects",
};

export function describeOp(o: EditOp): string {
  const f = o.fields ? Object.entries(o.fields).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ") : "";
  return `${o.op} ${o.kind} ${o.id ?? ""} ${f}`.trim();
}

export function LayoutEditor({ layout, item, pending, onQueue, onClearPending, onApply, applying }: {
  layout: Layout;
  item: InspectedItem | null;
  pending: EditOp[];
  onQueue: (op: EditOp) => void;
  onClearPending: () => void;
  onApply: () => void;
  applying: boolean;
}) {
  const kind = item?.nodeKind && FIELDS[item.nodeKind] ? item.nodeKind : null;
  const current = kind && item?.id ? ((layout[COLLECTION[kind]] as unknown as Record<string, unknown>[]).find((x) => x.id === item.id) ?? null) : null;
  const [draft, setDraft] = useState<{ id: string; values: Record<string, string> }>({ id: "", values: {} });
  const values = current && draft.id === item?.id ? draft.values : {};
  const [addOpen, setAddOpen] = useState(false);
  const [nf, setNf] = useState({ room: layout.rooms[0]?.id ?? "", label: "", category: "box", w: "1", d: "0.6", h: "0.9", fx: "0.5", fz: "0.5" });

  function setField(k: string, v: string) {
    setDraft({ id: item?.id ?? "", values: { ...values, [k]: v } });
  }
  function queueSet() {
    if (!kind || !current || !item?.id) return;
    const fields: Record<string, unknown> = {};
    for (const def of FIELDS[kind]) {
      const raw = values[def.key];
      if (raw === undefined || raw === String(current[def.key] ?? "")) continue;
      if (def.type === "number") {
        const n = Number(raw);
        if (!Number.isFinite(n) || n <= 0) continue;
        fields[def.key] = n;
      } else fields[def.key] = raw;
    }
    if (Object.keys(fields).length === 0) return;
    onQueue({ op: "set", kind, id: item.id, fields });
    setDraft({ id: "", values: {} });
  }
  function queueAdd() {
    const n = (v: string) => Number(v);
    if (!nf.label.trim() || !nf.room) return;
    const id = `officer_${nf.label.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 24)}_${pending.length + 1}_${Date.now().toString(36).slice(-4)}`; // unique across sessions: an applied addition keeps its id
    onQueue({
      op: "add", kind: "fixture", id,
      fields: { label: nf.label.trim(), room: nf.room, category: nf.category || "box", footprint_m: [n(nf.w) || 1, n(nf.d) || 0.6], height_m: n(nf.h) || 0.9, position_frac: [Math.min(0.95, Math.max(0.05, n(nf.fx) || 0.5)), Math.min(0.95, Math.max(0.05, n(nf.fz) || 0.5))] },
    });
    setNf({ ...nf, label: "" });
  }

  return (
    <Section title="Correct the room (officer)">
      <p className="text-[10px] text-zinc-500">Measured or confirmed details replace the model&apos;s guesses. Every scenario is re-checked on the corrected scene; the earlier version is kept.</p>
      {kind && current ? (
        <div className="space-y-1.5">
          <div className="text-[11px] text-zinc-300">Editing <b>{String(current.label ?? item?.id)}</b> <span className="text-zinc-500">({kind})</span></div>
          {FIELDS[kind].map((d) => (
            <label key={d.key} className="flex items-center gap-2 text-[11px] text-zinc-400">
              <span className="w-32 shrink-0">{d.label}</span>
              {d.type === "select" ? (
                <select className="flex-1 bg-zinc-950 border border-zinc-700 rounded px-1 py-0.5" value={values[d.key] ?? String(current[d.key] ?? "")} onChange={(e) => setField(d.key, e.target.value)}>
                  {d.options!.map((o) => <option key={o}>{o}</option>)}
                </select>
              ) : (
                <input
                  className="flex-1 bg-zinc-950 border border-zinc-700 rounded px-1 py-0.5 text-zinc-100"
                  type={d.type === "number" ? "number" : "text"}
                  step="0.05"
                  value={values[d.key] ?? String(current[d.key] ?? "")}
                  onChange={(e) => setField(d.key, e.target.value)}
                />
              )}
            </label>
          ))}
          <div className="flex gap-2">
            <button onClick={queueSet} className="px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[11px]">Queue change</button>
            {kind !== "room" && (
              <button onClick={() => item?.id && onQueue({ op: "remove", kind, id: item.id })} className="px-2 py-1 rounded bg-zinc-800 hover:bg-red-900 text-[11px]">Queue removal</button>
            )}
          </div>
        </div>
      ) : (
        <div className="text-[11px] text-zinc-500">Click a room, door, object, camera or place in the 3D view to correct it.</div>
      )}
      <button className="text-[11px] text-indigo-300 underline" onClick={() => setAddOpen(!addOpen)}>{addOpen ? "Hide" : "Add"} an object I measured</button>
      {addOpen && (
        <div className="grid grid-cols-2 gap-1.5 text-[11px]">
          <select className="col-span-2 bg-zinc-950 border border-zinc-700 rounded px-1 py-0.5" value={nf.room} onChange={(e) => setNf({ ...nf, room: e.target.value })}>
            {layout.rooms.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
          </select>
          <input placeholder="What is it" className="bg-zinc-950 border border-zinc-700 rounded px-1 py-0.5" value={nf.label} onChange={(e) => setNf({ ...nf, label: e.target.value })} />
          <select className="bg-zinc-950 border border-zinc-700 rounded px-1 py-0.5" value={nf.category} onChange={(e) => setNf({ ...nf, category: e.target.value })}>
            {["box", "table", "chair", "shelf", "cabinet", "counter", "bed", "appliance", "safe"].map((c) => <option key={c}>{c}</option>)}
          </select>
          {([["w", "Width m"], ["d", "Depth m"], ["h", "Height m"], ["fx", "Position 0-1 (x)"], ["fz", "Position 0-1 (z)"]] as const).map(([k, l]) => (
            <input key={k} type="number" step="0.1" title={l} placeholder={l} className="bg-zinc-950 border border-zinc-700 rounded px-1 py-0.5" value={nf[k]} onChange={(e) => setNf({ ...nf, [k]: e.target.value })} />
          ))}
          <button onClick={queueAdd} className="px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700">Queue addition</button>
        </div>
      )}
      {pending.length > 0 && (
        <div className="space-y-1 pt-1 border-t border-zinc-800">
          <div className="text-[10px] uppercase text-violet-300">Pending changes ({pending.length})</div>
          {pending.map((o, i) => <div key={i} className="text-[10px] font-mono text-zinc-400 break-all">• {describeOp(o)}</div>)}
          <div className="flex gap-2">
            <button disabled={applying} onClick={onApply} className="px-2.5 py-1 rounded bg-violet-700 hover:bg-violet-600 disabled:opacity-50 text-[11px] font-semibold">
              {applying ? "Re-checking…" : "Apply and re-check all scenarios"}
            </button>
            <button onClick={onClearPending} className="px-2 py-1 rounded bg-zinc-800 text-[11px]">Discard</button>
          </div>
        </div>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------- photographs linked to scene objects

function PhotoCard({ caseId, photo, selectedId, showAll }: { caseId: string; photo: NonNullable<PhotoLinks["content"]>["photos"][number]; selectedId: string | null; showAll: boolean }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let made: string | null = null;
    let cancelled = false;
    api.evidenceFileUrl(caseId, photo.evidence_id).then((u: string) => {
      if (cancelled) URL.revokeObjectURL(u);
      else { made = u; setUrl(u); }
    }).catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; if (made) URL.revokeObjectURL(made); };
  }, [caseId, photo.evidence_id]);
  const shown = photo.matches.filter((m) => showAll || m.node_id === selectedId);
  return (
    <div className="space-y-1">
      <div className="text-[10px] text-zinc-500 font-mono truncate">{photo.filename}</div>
      <div className="relative border border-zinc-800 rounded overflow-hidden bg-black" data-testid="photo-card">
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt={photo.filename} className="w-full block" />
        ) : (
          <div className="h-24 flex items-center justify-center text-[10px] text-zinc-500">{failed ? "photo could not be loaded" : "loading photo…"}</div>
        )}
        {url && shown.map((m, i) => (
          <div
            key={i}
            data-testid="photo-box"
            title={`${m.label} (detected as "${m.term}")`}
            className={`absolute border-2 ${m.node_id === selectedId ? "border-amber-400 bg-amber-400/10" : "border-cyan-400/80"}`}
            style={{ left: `${m.pct[0]}%`, top: `${m.pct[1]}%`, width: `${m.pct[2]}%`, height: `${m.pct[3]}%` }}
          >
            <span className="absolute -top-4 left-0 text-[9px] bg-black/80 text-cyan-200 px-1 rounded whitespace-nowrap max-w-[160px] truncate">{m.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PhotoEvidence({ caseId, links, selectedId, canCreate, busy, onCreate }: {
  caseId: string; links: PhotoLinks | null; selectedId: string | null; canCreate: boolean; busy: boolean; onCreate: () => void;
}) {
  const [showAll, setShowAll] = useState(true);
  const content = links?.content ?? null;
  const total = content ? content.photos.reduce((n, p) => n + p.matches.length, 0) : 0;
  return (
    <Section title="Objects found in the case photographs">
      {!content ? (
        <p className="text-[11px] text-zinc-500">
          {canCreate ? "Meta's SAM 3.1 can find the scene's objects in the case photographs, so you can check each one against the photo that supports it." : "No photograph links have been made for this scene."}
        </p>
      ) : (
        <>
          <p className="text-[10px] text-zinc-500">
            {total} possible match(es) in {content.photos.length} photograph(s), found by {content.detector}. {content.caveat}
            {content.calls_failed > 0 ? ` ${content.calls_failed} of ${content.calls} detector calls failed, so some objects may be missing.` : ""}
          </p>
          {links?.stale && <p className="text-[11px] text-orange-300">The room layout has changed since these were made. Run the search again.</p>}
          <label className="flex items-center gap-1 text-[11px] text-zinc-400"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> Show every match (otherwise only the selected object)</label>
          <div className="space-y-2">
            {content.photos.map((p) => <PhotoCard key={p.evidence_id} caseId={caseId} photo={p} selectedId={selectedId} showAll={showAll} />)}
          </div>
        </>
      )}
      {canCreate && (
        <button disabled={busy} onClick={onCreate} className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-[11px] font-semibold">
          {busy ? "Searching the photographs…" : content ? "Search the photographs again" : "Find objects in the photographs"}
        </button>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------- the second model's review

const SEV_STYLE: Record<string, string> = {
  problem: "border-red-800 bg-red-950/40 text-red-200",
  concern: "border-amber-800 bg-amber-950/30 text-amber-200",
  note: "border-zinc-700 bg-zinc-900 text-zinc-300",
};
const VERDICT_TEXT: Record<string, string> = {
  problems: "The reviewer found problems",
  concerns: "The reviewer has concerns",
  notes_only: "Only minor notes",
  nothing_found: "The reviewer found nothing it could point at",
  not_reviewed: "Could not be reviewed",
};

function FrameThumb({ caseId, reviewId, name, label }: { caseId: string; reviewId: string; name: string; label: string }) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const made = useRef<string | null>(null);
  useEffect(() => {
    if (!open || made.current) return;
    let cancelled = false;
    api.reviewFrameUrl(caseId, reviewId, name).then((u: string) => {
      if (cancelled) URL.revokeObjectURL(u);
      else { made.current = u; setUrl(u); }
    }).catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [open, caseId, reviewId, name]);
  // the picture's address is released only when this thumbnail goes away, not when it finishes loading
  useEffect(() => () => { if (made.current) URL.revokeObjectURL(made.current); }, []);
  return (
    <span>
      <button onClick={() => setOpen(!open)} className={`px-1.5 py-0.5 rounded border text-[10px] font-mono ${open ? "bg-indigo-900 border-indigo-600 text-indigo-100" : "bg-zinc-900 border-zinc-700 text-zinc-300 hover:border-zinc-500"}`}>{label}</button>
      {open && (
        <div className="mt-1.5 border border-zinc-700 rounded overflow-hidden bg-black" data-testid="review-frame">
          {url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={url} alt={`plan view ${label}`} className="w-full block" />
          ) : (
            <div className="h-16 flex items-center justify-center text-[10px] text-zinc-500">{failed ? "picture not available" : "loading…"}</div>
          )}
        </div>
      )}
    </span>
  );
}

export function ReviewPanel({ caseId, review, scenarioId, evidenceIndex, canStart, busy, onStart }: {
  caseId: string; review: SandboxReview | null; scenarioId: string; evidenceIndex: Record<string, EvidenceEntry>; canStart: boolean; busy: boolean; onStart: () => void;
}) {
  const mine = review?.content?.scenarios.find((s) => s.scenario_id === scenarioId) ?? null;
  const running = review?.status === "running";
  return (
    <Section title="Second-model review" tone={mine?.verdict === "problems" ? "bad" : mine?.verdict === "concerns" ? "warn" : "default"}>
      {!review || review.status === "none" ? (
        <p className="text-[11px] text-zinc-500">A second model can read this scenario next to the evidence it cites, the case photographs and plan-view pictures of the scene at about two dozen moments, and say what does not fit. It is an opinion, checked only for whether each point refers to something real.</p>
      ) : running ? (
        <p className="text-[11px] text-sky-300 animate-pulse">The reviewer is reading the scenarios and looking at the pictures. This takes a few minutes; you can keep working.</p>
      ) : review.status === "failed" ? (
        <p className="text-[11px] text-red-300">The review could not be completed. {review.message}</p>
      ) : !mine ? (
        <p className="text-[11px] text-zinc-500">This scenario was not part of the last review.</p>
      ) : (
        <div className="space-y-2">
          {review.stale && <p className="text-[11px] text-orange-300">The scene has been rebuilt since this review. Run it again.</p>}
          <div className="text-[11px] text-zinc-300">
            <b>{VERDICT_TEXT[mine.verdict]}</b>
            <span className="text-zinc-500"> · {mine.frames.length} pictures{mine.photos_sent ? ` and ${mine.photos_sent} photographs` : ""} · {mine.reviewed_with_images ? "looked at the pictures" : "text only, no pictures"}{mine.model ? ` · ${mine.model}` : ""}</span>
          </div>
          {mine.batches_failed > 0 && <p className="text-[11px] text-amber-300">{mine.batches_failed} of {mine.batches} parts of the review failed, so it may be incomplete.</p>}
          {mine.findings.map((f, i) => (
            <div key={i} className={`border rounded p-2 text-[11px] space-y-1 ${SEV_STYLE[f.severity] ?? SEV_STYLE.note}`} data-testid="review-finding">
              <div className="flex flex-wrap gap-1.5 items-center text-[10px] uppercase tracking-wide opacity-80">
                <span>{f.severity}</span><span>· {f.type.replace(/_/g, " ")}</span>{f.step !== null && <span>· step {f.step}</span>}{f.person && <span>· {f.person}</span>}
              </div>
              <div className="leading-relaxed">{f.text}</div>
              {f.suggested_fix && <div className="opacity-80">Suggested: {f.suggested_fix}</div>}
              {f.evidence_refs.length > 0 && <RefChips refs={f.evidence_refs} index={evidenceIndex} />}
              {f.frames.length > 0 && review.review_id && (
                <div className="flex flex-wrap gap-1.5">
                  {f.frames.map((fid) => (mine.frame_files[fid] ? <FrameThumb key={fid} caseId={caseId} reviewId={review.review_id as string} name={mine.frame_files[fid]} label={fid} /> : null))}
                </div>
              )}
            </div>
          ))}
          {mine.findings.length === 0 && <p className="text-[11px] text-zinc-400">Nothing was reported that points at a real step, picture or piece of evidence. That is not proof the scenario is right.</p>}
          {mine.dropped_findings > 0 && <p className="text-[10px] text-zinc-500">{mine.dropped_findings} point(s) were dropped because they referred to nothing that exists.</p>}
          <p className="text-[10px] text-zinc-500">{mine.note}</p>
          {mine.frames.length > 0 && review.review_id && (
            <details className="text-[10px] text-zinc-500">
              <summary className="cursor-pointer">All {mine.frames.length} pictures the reviewer was shown</summary>
              <div className="mt-1 space-y-1">
                {mine.frames.map((fr) => (
                  <div key={fr.id} className="flex gap-2 items-start">
                    {mine.frame_files[fr.id] && <FrameThumb caseId={caseId} reviewId={review.review_id as string} name={mine.frame_files[fr.id]} label={fr.id} />}
                    <span>{fr.reason}</span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
      {canStart && !running && (
        <button disabled={busy} onClick={onStart} className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-[11px] font-semibold">
          {busy ? "Starting…" : review && review.status === "done" ? "Review again" : "Review with a second model"}
        </button>
      )}
    </Section>
  );
}
