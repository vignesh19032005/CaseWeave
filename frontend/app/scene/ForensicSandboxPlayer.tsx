"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { api, ApiError } from "../lib/api";
import { buildAxis, clockAt, daylightAt, formatDuration, fromDisplay, quietGaps, seenAt, solve, toDisplay, totalDuration } from "./sandboxSolver";
import type { CameraMode } from "./SandboxScene3D";
import type { LabelMode } from "./SandboxLabels";
import { BasisBadge, ComparisonMatrix, LayoutEditor, PhotoEvidence, RefChips, ReviewPanel, Section, SceneBoundary } from "./SandboxPanels";
import type { EditOp, InspectedItem, Layout, PhotoLinks, SandboxReview, SandboxState, Scenario } from "./sandboxTypes";

const SandboxScene3D = dynamic(() => import("./SandboxScene3D"), {
  ssr: false,
  loading: () => <div className="h-full flex items-center justify-center text-xs text-zinc-500">Loading 3D view…</div>,
});

function errMsg(e: unknown, fallback: string): string {
  return e instanceof ApiError || e instanceof Error ? e.message : fallback;
}

type Viewed = { run: SandboxState["run"]; scenarios: Scenario[] };

export default function ForensicSandboxPlayer({ caseId }: { caseId: string }) {
  const [state, setState] = useState<SandboxState | null>(null);
  const [loadError, setLoadError] = useState("");
  const [role, setRole] = useState("");
  const [viewRunId, setViewRunId] = useState<string | null>(null);
  const [viewed, setViewed] = useState<Viewed | null>(null);
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState("");

  const [activeId, setActiveId] = useState<string | null>(null);
  const [focusActor, setFocusActor] = useState<string | null>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const [camera, setCamera] = useState<CameraMode>("overview");
  const [cutaway, setCutaway] = useState(true);
  const [labelMode, setLabelMode] = useState<LabelMode>("minimal");
  const [dragMode, setDragMode] = useState<"rotate" | "move">("rotate");
  const [level, setLevel] = useState<number | null>(null);
  const [overlayAll, setOverlayAll] = useState(false);
  const [inspected, setInspected] = useState<InspectedItem | null>(null);
  const [focus, setFocus] = useState<[number, number, number] | null>(null);
  const [pending, setPending] = useState<EditOp[]>([]);
  const [photoLinks, setPhotoLinks] = useState<PhotoLinks | null>(null);
  const [review, setReview] = useState<SandboxReview | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);

  const [modal, setModal] = useState(false);
  const [hypothesis, setHypothesis] = useState("");
  const [questions, setQuestions] = useState<{ id: string; question: string; suggested_answers: string[] }[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [modalBusy, setModalBusy] = useState(false);
  const [modalError, setModalError] = useState("");
  const [showRetracted, setShowRetracted] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = (await api.getSandbox(caseId)) as SandboxState;
      setState(s);
      setLoadError("");
      if (s.status === "ready") {
        api.getPhotoLinks(caseId).then((p: PhotoLinks) => setPhotoLinks(p)).catch(() => undefined);
        api.getSandboxReview(caseId).then((v: SandboxReview) => setReview(v)).catch(() => undefined);
      }
    } catch (e) {
      setLoadError(errMsg(e, "Could not load the scene"));
    }
  }, [caseId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = (await api.getSandbox(caseId)) as SandboxState;
        if (!cancelled) {
          setState(s);
          setLoadError("");
        }
        if (s.status === "ready") {
          api.getPhotoLinks(caseId).then((p: PhotoLinks) => { if (!cancelled) setPhotoLinks(p); }).catch(() => undefined);
          api.getSandboxReview(caseId).then((v: SandboxReview) => { if (!cancelled) setReview(v); }).catch(() => undefined);
        }
      } catch (e) {
        if (!cancelled) setLoadError(errMsg(e, "Could not load the scene"));
      }
      try {
        const m = (await api.me()) as { role?: string };
        if (!cancelled) setRole(m?.role ?? "");
      } catch {
        if (!cancelled) setRole("");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  useEffect(() => {
    if (state?.status !== "generating") return;
    const id = setInterval(() => void load(), 3000);
    return () => clearInterval(id);
  }, [state?.status, load]);

  useEffect(() => {
    if (review?.status !== "running") return;
    const id = setInterval(() => { api.getSandboxReview(caseId).then((v: SandboxReview) => setReview(v)).catch(() => undefined); }, 4000);
    return () => clearInterval(id);
  }, [review?.status, caseId]);

  useEffect(() => {
    if (!viewRunId) return;
    api.getSandboxRun(caseId, viewRunId).then((r: Viewed) => setViewed(r)).catch((e: unknown) => setActionError(errMsg(e, "Could not open that version")));
  }, [viewRunId, caseId]);

  const viewedNow = viewRunId && viewed?.run?.run_id === viewRunId ? viewed : null;
  const run = viewedNow ? viewedNow.run : state?.run ?? null;
  const layout: Layout | null = run?.layout ?? null;
  const allScenarios = useMemo(() => (viewedNow ? viewedNow.scenarios : state?.scenarios ?? []), [viewedNow, state]);
  const scenarios = useMemo(() => allScenarios.filter((s) => s.status === "active"), [allScenarios]);
  const retracted = useMemo(() => allScenarios.filter((s) => s.status === "retracted"), [allScenarios]);
  const scenario = scenarios.find((s) => s.scenario_id === activeId) ?? scenarios[0];
  const total = totalDuration(scenario);
  const [skipQuiet, setSkipQuiet] = useState(true);
  const [cinematic, setCinematic] = useState(false);
  const [pointView, setPointView] = useState(false);
  const axis = useMemo(() => buildAxis(total, skipQuiet ? quietGaps(scenario) : []), [scenario, total, skipQuiet]);
  const shown = (secs: number) => toDisplay(axis, secs) / Math.max(axis.display, 1e-9);
  const sim = useMemo(() => solve(scenario, t, focusActor), [scenario, t, focusActor]);
  const clock = clockAt(scenario, sim.t);
  const daylight = daylightAt(clock?.text);
  const seen = useMemo(() => seenAt(scenario?.visibility, sim.t), [scenario, sim.t]);
  const index = useMemo(() => ({ ...(run?.evidence_index ?? {}), ...(scenario?.evidence_index ?? {}) }), [run, scenario]);
  const overlay = useMemo(() => (overlayAll ? scenarios.filter((s) => s.scenario_id !== scenario?.scenario_id) : []), [overlayAll, scenarios, scenario]);
  const canGenerate = role === "investigator" || role === "admin";
  const canApprove = role === "reviewer" || role === "admin";
  const canExport = role === "admin";
  const readOnly = Boolean(viewedNow);
  const cameras = layout?.observers.filter((o) => o.kind === "camera") ?? [];
  const observerId = camera.startsWith("observer:") ? camera.slice(9) : null;
  const observer = observerId ? layout?.observers.find((o) => o.id === observerId) : undefined;
  const primary = sim.primary;

  const raf = useRef<number | null>(null);
  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setT((p) => {
        const n = fromDisplay(axis, toDisplay(axis, p) + dt * speed);   // moves along the shortened clock, so quiet stretches pass in a blink
        if (n >= total - 1e-6) {
          setPlaying(false);
          return total;
        }
        return n;
      });
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [playing, speed, total, axis]);

  function pick(id: string) {
    setActiveId(id);
    setT(0);
    setPlaying(false);
    setInspected(null);
    setFocus(null);
    setFocusActor(null);
  }

  async function guarded(name: string, fn: () => Promise<void>, fallback: string) {
    setActionError("");
    setBusy(name);
    try {
      await fn();
    } catch (e) {
      setActionError(errMsg(e, fallback));
    } finally {
      setBusy("");
    }
  }

  const startGeneration = (mode: "full" | "scenarios_only") =>
    guarded(mode, async () => {
      await api.generateSandbox(caseId, mode);
      setViewRunId(null);
      await load();
    }, "Could not start generation");

  const approve = () => guarded("approve", async () => { await api.approveSandboxLayout(caseId); await load(); }, "Could not approve the layout");
  const exportJson = () => guarded("export", () => api.downloadSandboxPack(caseId), "Could not export the review pack");
  const exportPdf = () => guarded("pdf", () => api.downloadSandboxPdf(caseId), "Could not export the PDF");
  const makePhotoLinks = () =>
    guarded("photos", async () => {
      await api.createPhotoLinks(caseId);
      setPhotoLinks((await api.getPhotoLinks(caseId)) as PhotoLinks);
    }, "Could not search the photographs");
  const startReview = () =>
    guarded("review", async () => {
      await api.startSandboxReview(caseId);
      setReview((await api.getSandboxReview(caseId)) as SandboxReview);
    }, "Could not start the review");
  const applyEdits = () =>
    guarded("edit", async () => {
      await api.editSandboxLayout(caseId, pending);
      setPending([]);
      setInspected(null);
      await load();
    }, "Could not apply the corrections");

  async function retract(s: Scenario) {
    const reason = window.prompt(`Why is "${s.title}" being withdrawn? (kept in the record)`);
    if (!reason || reason.trim().length < 5) return;
    await guarded("retract", async () => { await api.retractScenario(caseId, s.scenario_id, reason.trim()); await load(); }, "Could not withdraw the scenario");
  }

  async function askQuestions() {
    setModalBusy(true);
    setModalError("");
    try {
      const r = (await api.sandboxInterview(caseId, hypothesis)) as { questions: { id: string; question: string; suggested_answers: string[] }[] };
      setQuestions(r.questions);
      setAnswers({});
    } catch (e) {
      setModalError(errMsg(e, "Could not get questions"));
    } finally {
      setModalBusy(false);
    }
  }

  async function createOfficerScenario() {
    setModalBusy(true);
    setModalError("");
    try {
      const interview = questions.map((q) => ({ question: q.question, answer: answers[q.id] ?? "" }));
      const created = (await api.createOfficerScenario(caseId, hypothesis, interview)) as Scenario;
      await load();
      setModal(false);
      setHypothesis("");
      setQuestions([]);
      setAnswers({});
      pick(created.scenario_id);
    } catch (e) {
      setModalError(errMsg(e, "Could not build the scenario"));
    } finally {
      setModalBusy(false);
    }
  }

  if (!state && !loadError) {
    return <div className="p-8 text-center text-xs text-zinc-500">Loading scene…</div>;
  }
  if (!state) {
    return (
      <div className="p-4 border border-red-900 bg-red-950/30 rounded text-xs text-red-300">
        Could not load the scene: {loadError}{" "}
        <button className="underline" onClick={() => void load()}>Retry</button>
      </div>
    );
  }

  const status = state.status;
  const redaction = run?.generation?.redaction;
  const generateButtons = canGenerate && !readOnly && status !== "generating" && (
    <div className="flex gap-2 flex-wrap">
      <button disabled={Boolean(busy)} onClick={() => startGeneration("full")} className="px-3 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold">
        {status === "none" || status === "failed" ? "Generate scene from evidence" : "Rebuild scene from evidence"}
      </button>
      {status === "ready" && (
        <button disabled={Boolean(busy)} onClick={() => startGeneration("scenarios_only")} title="Keeps the current room layout and asks for new scenarios on it" className="px-3 py-1.5 rounded bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-100 text-xs font-semibold">
          New scenarios on this layout
        </button>
      )}
    </div>
  );

  return (
    <div className="flex flex-col border border-zinc-800 rounded-xl bg-zinc-950 overflow-hidden text-zinc-200">
      <div className="px-4 py-2 bg-amber-950/40 border-b border-amber-900/60 text-[11px] text-amber-200">{state.disclaimer}</div>

      {status === "ready" && !readOnly && scenarios.length > 0 && Math.max(...scenarios.map((s) => s.score.verifiable_score)) < 70 && (
        <div className="px-4 py-2 bg-amber-950/40 border-b border-amber-900 text-xs text-amber-200" data-testid="weak-banner">
          No scenario is strongly supported by the evidence yet (best: {Math.max(...scenarios.map((s) => s.score.verifiable_score))} out of 100). The score only counts what the evidence backs, so this usually means thin or conflicting evidence, not a faulty scene. Adding evidence, or testing an officer theory, can raise it.
        </div>
      )}
      {state.stale && status !== "generating" && !readOnly && (
        <div className="px-4 py-2 bg-orange-950/50 border-b border-orange-900 text-xs text-orange-200">
          The evidence has changed since this scene was generated, so it may not reflect the current record.
          {state.stale_detail ? ` ${state.stale_detail}` : ""} Rebuild to include the new material.
        </div>
      )}
      {status === "outdated" && (
        <div className="px-4 py-2 bg-orange-950/50 border-b border-orange-900 text-xs text-orange-200">
          This scene was built by an older version of the software and is not shown, because it could be misread. Rebuild it from the evidence (the old version stays in the history).
        </div>
      )}
      {readOnly && run && (
        <div className="px-4 py-2 bg-sky-950/50 border-b border-sky-900 text-xs text-sky-200 flex items-center justify-between">
          <span>Viewing an earlier version ({run.status}), generated {run.created_at}. Read-only.</span>
          <button className="underline" onClick={() => setViewRunId(null)}>Back to current</button>
        </div>
      )}
      {(actionError || state.last_failure) && (
        <div className="px-4 py-2 bg-red-950/40 border-b border-red-900 text-xs text-red-300">
          {actionError || `The last attempt failed: ${state.last_failure?.message}`}
        </div>
      )}

      {status === "generating" && (
        <div className="p-10 text-center text-sm text-zinc-400 space-y-2">
          <div className="animate-spin w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full mx-auto" />
          <div>Building the scene from this case&apos;s evidence. This usually takes one to two minutes.</div>
          <div className="text-[11px] text-zinc-500">You can keep working; this panel updates by itself.</div>
        </div>
      )}

      {(status === "none" || status === "failed" || status === "outdated") && (
        <div className="p-8 text-center space-y-3">
          {status !== "outdated" && <div className="text-sm text-zinc-300">No scene has been generated for this case yet.</div>}
          <p className="text-[11px] text-zinc-500 max-w-xl mx-auto">
            The scene is built only from the evidence already analysed for this case. Nothing is generated until an investigator asks for it.
            {state.redaction_default ? " Names, phone numbers and other identifiers are replaced with placeholders before anything is sent to an AI service." : ""}
          </p>
          {generateButtons ? <div className="flex justify-center">{generateButtons}</div> : <div className="text-xs text-zinc-500">An investigator or admin can generate the scene.</div>}
        </div>
      )}

      {status === "insufficient_evidence" && (
        <div className="p-8 text-center space-y-3">
          <div className="text-sm text-amber-300">The evidence does not support building a scene.</div>
          <p className="text-xs text-zinc-400 max-w-xl mx-auto">{run?.status_message || run?.assessment?.reason}</p>
          {generateButtons && <div className="flex justify-center">{generateButtons}</div>}
        </div>
      )}

      {status === "ready" && layout && (
        <>
          <div className="p-3 bg-zinc-900 border-b border-zinc-800 flex flex-wrap items-center gap-2 justify-between">
            <div className="flex flex-wrap items-center gap-1.5">
              {scenarios.map((s) => (
                <button
                  key={s.scenario_id}
                  onClick={() => pick(s.scenario_id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 border ${scenario?.scenario_id === s.scenario_id ? "bg-indigo-600 border-indigo-500 text-white" : "bg-zinc-950 border-zinc-800 text-zinc-300 hover:text-white"}`}
                >
                  <span className="text-[10px] opacity-80">{s.scenario_type === "officer_custom" ? "OFFICER" : `#${s.rank}`}</span>
                  <span className="truncate max-w-[200px]">{s.title}</span>
                  {s.support_level === "less_supported" && <span title="Takes an alternative the evidence supports less well" className="text-[9px] px-1 rounded bg-amber-950 text-amber-300 border border-amber-800">less supported</span>}
                  <span className={`text-[10px] px-1.5 rounded font-mono ${s.validation.is_physically_possible ? "bg-emerald-950 text-emerald-300" : "bg-red-950 text-red-300"}`}>{s.score.verifiable_score}</span>
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {run?.generation?.provider_mode !== "local_only" && (run?.generation?.calls ?? []).some((c) => c.provider === "local") && (
                <span title="Meta's hosted model could not answer, so the local model on this network was used for these steps. It is smaller, so check the scenarios more carefully." className="px-2 py-0.5 rounded border border-amber-800 bg-amber-950 text-amber-300 text-[10px]">
                  local model used for {(run?.generation?.calls ?? []).filter((c) => c.provider === "local").length} step(s)
                </span>
              )}
              {run?.generation?.provider_mode && run.generation.provider_mode !== "auto" && (
                <span title={run.generation.provider_mode === "local_only" ? "Every AI call for this scene ran on the department's own server" : "Only Meta's models were used for this scene"} className="px-2 py-0.5 rounded border border-sky-800 bg-sky-950 text-sky-300 text-[10px]">
                  {run.generation.provider_mode === "local_only" ? "on-premise model" : "Meta models only"}
                </span>
              )}
              {run?.generation?.evidence?.guard && run.generation.evidence.guard.removed > 0 && (
                <span title={`${run.generation.evidence.guard.findings.map((f) => f.kind).join(", ")}. ${run.generation.evidence.guard.note}`} className="px-2 py-0.5 rounded border border-amber-800 bg-amber-950 text-amber-300 text-[10px]">
                  {run.generation.evidence.guard.removed} instruction-like text(s) removed
                </span>
              )}
              {redaction?.enabled && (
                <span title={`Replaced before sending to AI: ${Object.entries(redaction.replacements).map(([k, v]) => `${v} ${k}`).join(", ") || "nothing found"}. Not covered: ${redaction.not_covered.join("; ")}`} className="px-2 py-0.5 rounded border border-emerald-800 bg-emerald-950 text-emerald-300 text-[10px]">
                  identifiers redacted
                </span>
              )}
              {state.history.length > 1 && (
                <select value={viewRunId ?? ""} onChange={(e) => setViewRunId(e.target.value || null)} className="bg-zinc-950 border border-zinc-700 rounded px-2 py-1 text-[11px]" title="Earlier versions are never deleted">
                  <option value="">Current version</option>
                  {state.history.filter((h) => !h.is_current).map((h) => (
                    <option key={h.run_id} value={h.run_id}>{h.created_at} · {h.status}</option>
                  ))}
                </select>
              )}
              {canApprove && !readOnly && !run?.approved_by && (
                <button onClick={approve} disabled={busy === "approve"} className="px-2.5 py-1 rounded bg-emerald-800 hover:bg-emerald-700 text-[11px] font-semibold disabled:opacity-50">Approve room layout</button>
              )}
              {canGenerate && !readOnly && (
                <>
                  <button onClick={() => setModal(true)} className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[11px] font-semibold">Test an officer theory</button>
                  <button onClick={() => setEditorOpen(!editorOpen)} className={`px-2.5 py-1 rounded text-[11px] font-semibold ${editorOpen ? "bg-violet-700" : "bg-zinc-800 hover:bg-zinc-700"}`}>Correct the room</button>
                </>
              )}
              {canExport && (
                <>
                  <button onClick={exportPdf} disabled={busy === "pdf"} className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[11px] font-semibold disabled:opacity-50">Export PDF</button>
                  <button onClick={exportJson} disabled={busy === "export"} className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-[11px] font-semibold disabled:opacity-50">Export JSON pack</button>
                </>
              )}
              {generateButtons}
            </div>
          </div>

          {!scenario ? (
            <div className="p-8 text-center text-xs text-zinc-500">This scene has no active scenarios.</div>
          ) : (
            <>
              <div className="px-4 py-2 bg-zinc-950 border-b border-zinc-800/80 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="px-2.5 py-1 rounded bg-zinc-900 border border-zinc-800 font-mono text-xs text-emerald-400" title={clock ? "Clock time comes from the case record at steps that cite timed evidence; between those it is an estimate" : "No step cites a timed observation, so no real clock time is shown"}>
                    {clock ? `${clock.text}${clock.estimated ? " est." : ""}` : "no clock"}
                    <span className="ml-2 text-[10px] text-zinc-500">{formatDuration(sim.t)} / {formatDuration(total)}</span>
                    {axis.skipped > 1 && <span className="ml-2 text-[10px] text-sky-400" title="Playback skips long stretches where nobody is doing anything. Untick 'Skip quiet periods' to play it all.">skips {formatDuration(axis.skipped)}</span>}
                  </div>
                  {primary && (
                    <span className="text-xs text-zinc-200 font-semibold truncate max-w-md">
                      {primary.kind === "transit" ? `${primary.label} walking to ${primary.placeLabel}` : `${primary.label}: ${primary.phase || primary.placeLabel}`}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-wrap text-xs">
                  <button onClick={() => { setPlaying(false); setT(0); }} className="px-2 py-1 rounded bg-zinc-900 hover:bg-zinc-800" title="Restart">⏮</button>
                  <button onClick={() => { if (t >= total) setT(0); setPlaying(!playing); }} className={`px-3.5 py-1 rounded font-bold ${playing ? "bg-amber-600" : "bg-emerald-600"} text-white`}>{playing ? "Pause" : "Play"}</button>
                  <div className="flex border border-zinc-800 rounded bg-zinc-900 p-0.5 text-[10px]">
                    {[1, 2, 5, 10].map((v) => (
                      <button key={v} onClick={() => setSpeed(v)} className={`px-1.5 py-0.5 rounded ${speed === v ? "bg-indigo-600 text-white" : "text-zinc-400"}`}>{v}x</button>
                    ))}
                  </div>
                  <select value={camera} onChange={(e) => { setCamera(e.target.value as CameraMode); setFocus(null); }} className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1" aria-label="Camera">
                    <option value="overview">Overview</option>
                    <option value="topdown">Top-down</option>
                    <option value="follow">Follow the selected person</option>
                    {cameras.map((c) => <option key={c.id} value={`observer:${c.id}`}>CCTV: {c.label}</option>)}
                  </select>
                  {layout.levels.length > 1 && (
                    <select value={level === null ? "all" : String(level)} onChange={(e) => setLevel(e.target.value === "all" ? null : Number(e.target.value))} className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1" aria-label="Floor">
                      <option value="all">All floors</option>
                      {layout.levels.map((l) => <option key={l.level} value={l.level}>Up to floor {l.level}</option>)}
                    </select>
                  )}
                  <div className="flex border border-zinc-800 rounded bg-zinc-900 p-0.5 text-[10px]" title="What dragging with the left mouse button does. Right-drag always moves the view; the wheel zooms.">
                    {(["rotate", "move"] as const).map((m) => (
                      <button key={m} onClick={() => setDragMode(m)} className={`px-1.5 py-0.5 rounded ${dragMode === m ? "bg-indigo-600 text-white" : "text-zinc-400"}`}>{m === "rotate" ? "Rotate" : "Move"}</button>
                    ))}
                  </div>
                  <label className="flex items-center gap-1 text-[11px] text-zinc-400" title="Soft contact shadows, a gentle glow and a film-style tone. It only changes how the scene is drawn. Slower on weak graphics cards."><input type="checkbox" checked={cinematic} onChange={(e) => setCinematic(e.target.checked)} /> Cinematic</label>
                  <label className="flex items-center gap-1 text-[11px] text-zinc-400" title="Redraws the scene as dots for a scan-like look. It is a stylised view of the same model, not scan data and not a measurement."><input type="checkbox" checked={pointView} onChange={(e) => setPointView(e.target.checked)} /> Point view (stylised)</label>
                  <label className="flex items-center gap-1 text-[11px] text-zinc-400" title="Skips long stretches where nobody is doing anything, keeping the first and last moments of each"><input type="checkbox" checked={skipQuiet} onChange={(e) => setSkipQuiet(e.target.checked)} /> Skip quiet periods</label>
                  <label className="flex items-center gap-1 text-[11px] text-zinc-400"><input type="checkbox" checked={cutaway} onChange={(e) => setCutaway(e.target.checked)} /> Cutaway walls</label>
                  <label className="flex items-center gap-1 text-[11px] text-zinc-400" title="Minimal: people, the active place and what you select. All: every object, door and camera. Labels move out of the way of people and fade while you drag.">
                    Labels
                    <select value={labelMode} onChange={(e) => setLabelMode(e.target.value as LabelMode)} className="bg-zinc-900 border border-zinc-700 rounded px-1 py-0.5" aria-label="Labels">
                      <option value="off">Off</option>
                      <option value="minimal">Minimal</option>
                      <option value="all">All</option>
                    </select>
                  </label>
                </div>
              </div>

              <div className="px-4 py-2 bg-zinc-900/90 border-b border-zinc-800">
                <input type="range" min={0} max={axis.display} step={0.1} value={Math.min(toDisplay(axis, t), axis.display)} onChange={(e) => { setT(fromDisplay(axis, parseFloat(e.target.value))); setPlaying(false); }} className="w-full accent-emerald-500" aria-label="Scenario time" />
                <div className="relative h-4 mt-0.5">
                  {axis.pieces.filter((p) => p.gap).map((p) => (
                    <span key={`gap-${p.t0}`} title={`Nothing happens between ${formatDuration(p.t0)} and ${formatDuration(p.t1)}; the middle is skipped when you play`} className="absolute top-0 -translate-x-1/2 text-[10px] text-zinc-500 select-none" style={{ left: `${((p.d0 + (p.d1 - p.d0) / 2) / Math.max(axis.display, 1e-9)) * 100}%` }} data-testid="skip-marker">
                      ⋯ {formatDuration(p.t1 - p.t0 - (p.d1 - p.d0))} skipped
                    </span>
                  ))}
                  {scenario.plan.actors.filter((a) => !focusActor || a.id === focusActor).flatMap((a) => a.steps.map((st) => ({ a, st }))).map(({ a, st }) => (
                    <button
                      key={`${a.id}-${st.k}`}
                      onClick={() => { setT(st.arrive_s); setPlaying(false); }}
                      title={`${a.label}: ${st.k + 1}. ${st.label} (${st.action})`}
                      className="absolute top-0 -translate-x-1/2 text-[9px] w-4 h-4 rounded-full border text-black"
                      style={{ left: `${shown(st.arrive_s) * 100}%`, background: a.color, borderColor: sim.actors.find((x) => x.id === a.id)?.step === st.k ? "#fff" : "#27272a" }}
                    >
                      {st.k + 1}
                    </button>
                  ))}
                </div>
                {scenario.plan.actors.length > 1 && (
                  <div className="flex flex-wrap gap-2 mt-1 text-[10px]">
                    <button onClick={() => setFocusActor(null)} className={`px-1.5 rounded border ${focusActor === null ? "border-indigo-500 text-indigo-200" : "border-zinc-700 text-zinc-400"}`}>everyone</button>
                    {scenario.plan.actors.map((a) => (
                      <button key={a.id} onClick={() => setFocusActor(a.id)} className={`px-1.5 rounded border flex items-center gap-1 ${focusActor === a.id ? "border-indigo-500 text-indigo-200" : "border-zinc-700 text-zinc-400"}`}>
                        <span className="inline-block w-2 h-2 rounded-full" style={{ background: a.color }} />
                        {a.label} <span className="text-zinc-500">({a.role})</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 h-[680px]">
                <div className="lg:col-span-2 relative bg-[#0b1020] h-full">
                  <SceneBoundary resetKey={`${run?.run_id}-${scenario.scenario_id}`}>
                    <SandboxScene3D
                      layout={layout} scenario={scenario} overlay={overlay} sim={sim} cutaway={cutaway} labelMode={labelMode}
                      camera={camera} focus={focus} selectedId={inspected?.id ?? null} maxLevel={level} daylight={daylight} seen={seen} cinematic={cinematic} pointView={pointView} dragMode={dragMode}
                      onInspect={(i) => { setInspected(i); if (i.focus) setFocus(i.focus); }}
                    />
                  </SceneBoundary>
                  {observer && (
                    <div className="absolute inset-x-0 top-0 p-2 flex justify-between pointer-events-none font-mono text-[11px] text-white" style={{ textShadow: "0 0 3px #000" }}>
                      <span><span className="text-red-500">●</span> REC · {observer.label}{seen[observer.id]?.length ? <span className="ml-3 px-1.5 rounded bg-red-600 text-white animate-pulse">MOTION DETECTED · {seen[observer.id].join(", ")}</span> : null}</span>
                      <span>{clock ? `${clock.text}${clock.estimated ? " (est.)" : ""}` : "no clock"}</span>
                    </div>
                  )}
                  <div className="absolute bottom-2 left-2 flex gap-1.5 text-[10px] pointer-events-none flex-wrap">
                    <span className="px-2 py-0.5 rounded bg-zinc-950/85 border border-zinc-800 text-emerald-400">green: direct route</span>
                    <span className="px-2 py-0.5 rounded bg-zinc-950/85 border border-zinc-800 text-amber-400">amber: adjusted by system</span>
                    <span className="px-2 py-0.5 rounded bg-zinc-950/85 border border-zinc-800 text-rose-300">red outline: assumed object</span>
                    {pointView && <span className="px-2 py-0.5 rounded bg-amber-950/90 border border-amber-800 text-amber-300">Point view: stylised dots drawn from the model, not scan data</span>}
                  </div>
                </div>

                <div className="p-3 bg-zinc-950 border-t lg:border-t-0 lg:border-l border-zinc-800 overflow-y-auto space-y-2.5">
                  {editorOpen && canGenerate && !readOnly && (
                    <LayoutEditor layout={layout} item={inspected} pending={pending} onQueue={(op) => setPending((p) => [...p, op])} onClearPending={() => setPending([])} onApply={applyEdits} applying={busy === "edit"} />
                  )}
                  {inspected && (
                    <Section title={`Selected: ${inspected.title}`}>
                      <div className="flex items-center gap-2 text-[10px] text-zinc-400">
                        <span>{inspected.kind}</span>
                        {inspected.basis && <BasisBadge basis={inspected.basis} />}
                        <button className="ml-auto text-zinc-500 hover:text-white" onClick={() => setInspected(null)}>close</button>
                      </div>
                      <p className="text-xs text-zinc-300 leading-relaxed">{inspected.description}</p>
                      {inspected.notes?.map((n, i) => <p key={i} className="text-[11px] text-amber-300">• {n}</p>)}
                      {inspected.refs && <RefChips refs={inspected.refs} index={index} />}
                    </Section>
                  )}

                  {scenario.revalidation_note && <div className="text-[11px] text-sky-300 p-2 border border-sky-900 rounded">{scenario.revalidation_note}</div>}

                  <Section title={scenario.scenario_type === "officer_custom" ? "Officer theory" : `Candidate #${scenario.rank}`}>
                    <p className="text-xs text-zinc-200 leading-relaxed">{scenario.hypothesis_summary}</p>
                    {scenario.strengthened && <p className="text-[11px] text-emerald-300">Improved once with evidence it had left unused: the support score rose from {scenario.strengthened.from_score} to {scenario.strengthened.to_score}.</p>}
                    {scenario.repair && <p className="text-[11px] text-sky-300">{scenario.repair.method === "tool_calling" ? `Repaired by a Meta model that called the checker as a tool ${scenario.repair.checks ?? 0} time(s); the checker, not the model, chose the version kept` : "Repaired once for logical problems the checker found"} ({scenario.repair.problems_left} left).</p>}
                    {scenario.differs_by && <p className="text-[11px] text-indigo-300">What is different about this one: {scenario.differs_by}</p>}
                    {scenario.support_level === "less_supported" && <p className="text-[11px] text-amber-300">This is a less supported possibility: it takes an alternative the evidence leans away from. It is shown so you can test it, not because it is the likeliest.</p>}
                    {scenario.support_level === "alternative" && <p className="text-[11px] text-sky-300">An alternative reading of a question the evidence leaves open.</p>}
                    {scenario.officer_input && <p className="text-[11px] text-zinc-400">Proposed by {scenario.officer_input.submitted_by}: &ldquo;{scenario.officer_input.hypothesis}&rdquo;</p>}
                    {scenario.scenario_type === "officer_custom" && canGenerate && !readOnly && (
                      <button onClick={() => retract(scenario)} className="text-[11px] text-red-400 hover:underline">Withdraw this scenario (kept in the record)</button>
                    )}
                  </Section>

                  <PhotoEvidence caseId={caseId} links={photoLinks} selectedId={inspected?.id ?? null} canCreate={canGenerate && !readOnly} busy={busy === "photos"} onCreate={makePhotoLinks} />

                  <ComparisonMatrix scenarios={scenarios} activeId={scenario.scenario_id} onPick={pick} overlay={overlayAll} setOverlay={setOverlayAll} />

                  <Section title="Now" tone="good">
                    {sim.actors.map((a) => (
                      <div key={a.id} className="text-xs text-zinc-200">
                        <span className="inline-block w-2 h-2 rounded-full mr-1" style={{ background: a.color }} />
                        <b>{a.label}</b>: {!a.started ? "not yet on scene" : a.ended ? `no further steps; last shown ${a.action.replace("_", " ")} at ${a.placeLabel}` : a.kind === "transit" ? `walking to ${a.placeLabel}` : `${a.action.replace("_", " ")} at ${a.placeLabel}`}
                        {a.started && !a.ended && a.narrative && <div className="text-[11px] text-zinc-400 ml-3">{a.narrative}</div>}
                        {a.started && !a.ended && a.routingNotes.length > 0 && <div className="text-[11px] text-amber-300 ml-3">System routing: {a.routingNotes.join("; ")}.</div>}
                      </div>
                    ))}
                    {primary && primary.kind === "dwell" && <RefChips refs={primary.evidenceRefs} index={index} />}
                  </Section>

                  <Section title="Evidence support score">
                    <div className="flex items-baseline gap-2">
                      <span className="text-2xl font-bold text-emerald-400">{scenario.score.verifiable_score}</span>
                      <span className="text-[11px] text-zinc-500">/ 100 · a ranking aid, not a probability</span>
                    </div>
                    <div className="text-[11px] text-zinc-400">
                      {Number(scenario.score.components.steps_citing_evidence)} of {Number(scenario.score.components.steps_total)} steps cite evidence · {Number(scenario.score.components.distinct_real_observations_cited)} distinct observations cited · {Number(scenario.score.components.contradictions)} point(s) against
                      {Number(scenario.score.components.steps_dropped_not_in_scene) > 0 && ` · ${Number(scenario.score.components.steps_dropped_not_in_scene)} step(s) could not be placed in the scene`}
                    </div>
                    {scenario.score.cap_reason && <div className="text-[11px] text-red-400">{scenario.score.cap_reason}</div>}
                    <div className="text-[10px] text-zinc-500">The model&apos;s own estimate was {scenario.score.llm_estimate}%. It is shown for reference and is not used for ranking.</div>
                    <details className="text-[10px] text-zinc-500"><summary className="cursor-pointer">How is this calculated?</summary><p className="mt-1">{scenario.score.formula}</p></details>
                  </Section>

                  <Section title={scenario.validation.is_physically_possible ? "Physical and timing checks: consistent" : `Physical and timing checks: ${scenario.validation.violations.length} problem(s)`} tone={scenario.validation.is_physically_possible ? "good" : "bad"}>
                    {scenario.validation.violations.map((v, i) => <div key={i} className="text-[11px] text-red-400">• {v.message}</div>)}
                    {scenario.validation.warnings.map((v, i) => <div key={i} className="text-[11px] text-amber-300">• {v}</div>)}
                    <div className="text-[11px] text-zinc-400">
                      {scenario.plan.total_distance_m.toFixed(1)} m walked in {formatDuration(scenario.plan.total_duration_s)} (pace is computed from distance, not supplied by the model).
                    </div>
                    {scenario.validation.observation_checks.length > 0 && (
                      <details className="text-[10px] text-zinc-500">
                        <summary className="cursor-pointer">Could the witnesses and cameras see this? ({scenario.validation.observation_checks.length})</summary>
                        <div className="mt-1 space-y-0.5">
                          {scenario.validation.observation_checks.map((c, i) => (
                            <div key={i} className={c.visible ? "text-emerald-400/80" : "text-red-400"}>{c.visible ? "✓" : "✗"} {c.label}: {c.reason}</div>
                          ))}
                        </div>
                      </details>
                    )}
                    <details className="text-[10px] text-zinc-500">
                      <summary className="cursor-pointer">What was and was not checked</summary>
                      <div className="mt-1 space-y-0.5">
                        {scenario.validation.checks_run.map((c, i) => <div key={i} className="text-emerald-400/80">✓ {c}</div>)}
                        {scenario.validation.checks_not_run.map((c, i) => <div key={i} className="text-zinc-400">○ not tested: {c}</div>)}
                      </div>
                    </details>
                  </Section>

                  <Section title={scenario.time.basis === "none" ? "No clock times" : scenario.time.basis === "officer" ? "Clock times from the officer" : "Clock times from the evidence"}>
                    <p className="text-[11px] text-zinc-400">{scenario.time.note}</p>
                    {scenario.time.anchors.map((a) => (
                      <div key={`${a.actor}-${a.step}-${a.observation_id}`} className="text-[11px] text-zinc-300">{a.actor_label}, step {a.step + 1} ({a.label}) at {a.clock_text} <span className="font-mono text-zinc-500">{a.observation_id}</span></div>
                    ))}
                    {[...scenario.time.cross_source_notes, ...scenario.time.cross_person_notes].map((n, i) => <div key={i} className="text-[11px] text-amber-300">• {n}</div>)}
                    {scenario.time.unmodelled_gaps.map((g, i) => <div key={i} className="text-[11px] text-amber-300">• {g.message}</div>)}
                    {scenario.unsupported_time_mentions.length > 0 && (
                      <div className="text-[11px] text-amber-300">Times mentioned with no timed evidence behind them: {scenario.unsupported_time_mentions.join(", ")}.</div>
                    )}
                  </Section>

                  {scenario.fidelity && (
                    <Section title="Does the simulation match the scenario?" tone={scenario.fidelity.round_trip_ok ? "good" : "bad"}>
                      <div className="text-[11px] text-zinc-300">
                        {scenario.fidelity.round_trip_ok ? "Yes. " : "No: "}
                        {scenario.fidelity.steps_in_simulation} of {scenario.fidelity.steps_given} steps shown
                        {scenario.fidelity.steps_not_placed > 0 ? ` (${scenario.fidelity.steps_not_placed} could not be placed in the scene)` : ""} · {scenario.fidelity.effects_in_simulation}/{scenario.fidelity.effects_expected} stated changes to doors and objects happen · {scenario.fidelity.people_shown} of {scenario.fidelity.people_listed} listed people shown.
                      </div>
                      {scenario.coverage && (
                        <div className="text-[11px] text-zinc-400">
                          Uses {scenario.coverage.key_used} of the {scenario.coverage.key_observations} most relevant observations.
                          {scenario.coverage.people_not_covered.length > 0 && <span className="text-amber-300"> Not covered: {scenario.coverage.people_not_covered.join(", ")}.</span>}
                        </div>
                      )}
                    </Section>
                  )}
                  <ReviewPanel caseId={caseId} review={review} scenarioId={scenario.scenario_id} evidenceIndex={index} canStart={canGenerate && !readOnly} busy={busy === "review"} onStart={startReview} />
                  {scenario.diversity && scenario.diversity.compared_with.length > 0 && (
                    <Section title="How different from the other scenarios">
                      {scenario.diversity.compared_with.map((c) => (
                        <div key={c.scenario_id} className="text-[11px] text-zinc-300">
                          vs #{c.rank}: {c.too_similar ? <span className="text-amber-300">very similar</span> : <span className="text-emerald-300">different</span>} ({c.distance.toFixed(2)}){c.differs_in.length > 0 && <span className="text-zinc-500"> — differs in {c.differs_in.join(", ")}</span>}
                        </div>
                      ))}
                    </Section>
                  )}

                  {(scenario.weak_citations.length > 0 || scenario.disputed_citations.length > 0 || scenario.citations_removed > 0 || scenario.narrative_consistency.facts_not_reflected?.length) && (
                    <Section title="Evidence cautions" tone="warn">
                      {scenario.citations_removed > 0 && <div className="text-[11px] text-red-400">{scenario.citations_removed} citation(s) did not exist in the case record and were removed.</div>}
                      {scenario.weak_citations.length > 0 && (
                        <div className="text-[11px] text-amber-300">Cited, but the cited text barely relates to the step: {scenario.weak_citations.map((w) => `${w.ref}${w.step !== null ? ` (step ${w.step + 1})` : ""}`).join(", ")}.</div>
                      )}
                      {scenario.disputed_citations.length > 0 && <div className="text-[11px] text-amber-300">Sources that conflict with others: {scenario.disputed_citations.join(", ")}.</div>}
                      {scenario.narrative_consistency.available && scenario.narrative_consistency.facts_not_reflected && scenario.narrative_consistency.facts_not_reflected.length > 0 && (
                        <div className="text-[11px] text-amber-300">
                          Facts in the saved incident narrative that this scenario does not reflect ({scenario.narrative_consistency.facts_not_reflected.length}/{scenario.narrative_consistency.facts_total}):
                          {scenario.narrative_consistency.facts_not_reflected.map((f, i) => <div key={i} className="ml-3">– {f}</div>)}
                        </div>
                      )}
                    </Section>
                  )}

                  {scenario.plan.actors.map((a) => (
                    <Section key={a.id} title={`${a.label} (${a.role}) · ${a.steps.length} step(s)`}>
                      <div className="space-y-1">
                        {a.steps.map((st) => (
                          <button key={st.k} onClick={() => { setT(st.arrive_s); setPlaying(false); setFocusActor(a.id); }} className={`w-full text-left p-1.5 rounded border text-[11px] ${sim.actors.find((x) => x.id === a.id)?.step === st.k ? "border-emerald-700 bg-emerald-950/30" : "border-zinc-800 hover:border-zinc-600"}`}>
                            <div className="flex items-center gap-1.5">
                              <span className="font-mono text-zinc-500">{st.k + 1}</span>
                              <span className="font-semibold text-zinc-200">{st.label}</span>
                              <span className="text-zinc-500">{st.action.replace("_", " ")}</span>
                              <span className={`ml-auto text-[9px] px-1 rounded border ${st.evidence_refs.length ? "border-emerald-800 text-emerald-300" : "border-zinc-700 text-zinc-500"}`}>
                                {st.evidence_refs.length ? `${st.evidence_refs.length} cited` : st.basis === "officer" ? "officer" : "inferred"}
                              </span>
                            </div>
                            {st.narrative && <div className="text-zinc-400 mt-0.5">{st.narrative}</div>}
                            {st.route_notes.length > 0 && <div className="text-amber-300/90 mt-0.5">{st.route_notes.join("; ")}</div>}
                          </button>
                        ))}
                      </div>
                    </Section>
                  ))}
                  {scenario.plan.dropped_steps.length > 0 && (
                    <div className="text-[11px] text-amber-300">Not shown (location is not part of the scene): {scenario.plan.dropped_steps.map((d) => d.node_id || "?").join(", ")}</div>
                  )}

                  {scenario.supporting_facts.length > 0 && (
                    <Section title="Supporting points" tone="good">
                      {scenario.supporting_facts.map((f, i) => (
                        <div key={i} className="text-[11px] text-zinc-300">
                          • {f.text}
                          <div className="ml-3 mt-0.5"><RefChips refs={f.refs} index={index} /></div>
                          {f.invalid_refs.length > 0 && <div className="ml-3 text-[10px] text-red-400">Removed {f.invalid_refs.length} citation(s) that do not exist in the case record.</div>}
                        </div>
                      ))}
                    </Section>
                  )}
                  {scenario.contradicted_points.length > 0 && (
                    <Section title="Points against, or unresolved" tone="warn">
                      {scenario.contradicted_points.map((f, i) => (
                        <div key={i} className="text-[11px] text-zinc-300">
                          <span className={`mr-1.5 px-1 rounded border text-[9px] uppercase ${f.kind === "open_question" ? "border-zinc-700 text-zinc-400" : "border-red-900 text-red-300"}`}>{f.kind === "open_question" ? "open question" : "contradicts"}</span>{f.text}
                          <div className="ml-3 mt-0.5"><RefChips refs={f.refs} index={index} /></div>
                        </div>
                      ))}
                    </Section>
                  )}

                  <Section title="How the scene was built">
                    <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
                      <span className="text-zinc-400">{layout.rooms.length} room(s) over {layout.levels.length} floor(s); sizes:</span> <BasisBadge basis={layout.dimensions_basis === "measured" ? "officer" : (layout.dimensions_basis as "stated" | "inferred" | "assumed")} />
                      <span className="text-emerald-300">{layout.coverage.stated} stated</span>
                      <span className="text-sky-300">{layout.coverage.inferred} inferred</span>
                      <span className="text-rose-300">{layout.coverage.assumed} assumed</span>
                      {layout.coverage.officer > 0 && <span className="text-violet-300">{layout.coverage.officer} officer</span>}
                    </div>
                    {layout.defaults_used.map((d, i) => <div key={i} className="text-[11px] text-rose-300">• {d}</div>)}
                    {layout.warnings.map((d, i) => <div key={i} className="text-[11px] text-amber-300">• {d}</div>)}
                    {layout.notes && <p className="text-[11px] text-zinc-400">Model note: {layout.notes}</p>}
                    {layout.limits.length > 0 && (
                      <details className="text-[10px] text-zinc-500"><summary className="cursor-pointer">What this scene does not model</summary>{layout.limits.map((l, i) => <div key={i}>• {l}</div>)}</details>
                    )}
                    {run?.generation?.vision_cues?.photos && run.generation.vision_cues.photos.length > 0 && (
                      <details className="text-[11px] text-zinc-400">
                        <summary className="cursor-pointer text-sky-300">Photo readings (inferred) · {run.generation.vision_cues.photos_read ?? run.generation.vision_cues.photos.length} of {run.generation.vision_cues.images_sent} photos</summary>
                        <p className="text-[10px] text-zinc-500">{run.generation.vision_cues.note}</p>
                        {run.generation.vision_cues.photos.map((ph) => (
                          <div key={ph.evidence_id} className="mt-1">
                            <div className="text-zinc-300">{ph.evidence_id} · {ph.filename}: {ph.scene}</div>
                            {ph.items.map((it, i) => <div key={i} className="pl-2">• {it.what} ({it.state}){it.note ? ` — ${it.note}` : ""}</div>)}
                            {ph.cannot_tell.length > 0 && <div className="pl-2 text-zinc-500">Cannot tell: {ph.cannot_tell.join("; ")}</div>}
                          </div>
                        ))}
                      </details>
                    )}
                    {run?.generation?.evidence && run.generation.evidence.observations_omitted > 0 && (
                      <p className="text-[11px] text-amber-300">{run.generation.evidence.observations_omitted} of {run.generation.evidence.observations_total} observations did not fit and were not shown to the model.</p>
                    )}
                    <p className="text-[10px] text-zinc-500">
                      {run?.approved_by ? `Layout approved by ${run.approved_by}${run.approved_at ? ` on ${run.approved_at}` : ""}.` : "Layout not yet approved by a reviewer."}
                      {" "}Generated {run?.created_at} by {run?.created_by ?? "system"} · {scenario.provenance.provider} / {scenario.provenance.model} · engine {scenario.engine_version ?? state.engine_version}
                    </p>
                  </Section>

                  {retracted.length > 0 && (
                    <div>
                      <button className="text-[11px] text-zinc-500 underline" onClick={() => setShowRetracted(!showRetracted)}>{showRetracted ? "Hide" : "Show"} {retracted.length} withdrawn scenario(s)</button>
                      {showRetracted && retracted.map((s) => (
                        <div key={s.scenario_id} className="mt-1 text-[11px] text-zinc-500">{s.title}: withdrawn by {s.retracted?.by} — {s.retracted?.reason}</div>
                      ))}
                    </div>
                  )}
                  {state.scenarios_on_other_layouts.length > 0 && (
                    <div className="text-[11px] text-zinc-500">{state.scenarios_on_other_layouts.length} officer scenario(s) were built on an earlier room layout and are not shown here; open the earlier version to see them.</div>
                  )}
                </div>
              </div>
            </>
          )}
        </>
      )}

      {modal && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
          <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-5 max-w-xl w-full space-y-3 max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-sm font-bold">Test an officer theory</h3>
                <p className="text-[11px] text-zinc-400">Describe what you think happened, including everyone involved. The system checks it against this scene and the evidence, and says plainly where it does not fit.</p>
              </div>
              <button className="text-zinc-400 hover:text-white" onClick={() => setModal(false)}>✕</button>
            </div>
            {modalError && <div className="p-2 rounded border border-red-800 bg-red-950 text-red-300 text-xs">{modalError}</div>}
            <textarea className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-xs text-white" rows={4} placeholder="Example: two people came in through the rear shutter; one searched the counter while the other watched the door, and they left by the front door." value={hypothesis} onChange={(e) => setHypothesis(e.target.value)} disabled={questions.length > 0} />
            {questions.length === 0 ? (
              <button disabled={modalBusy || hypothesis.trim().length < 10} onClick={askQuestions} className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-xs font-bold">{modalBusy ? "Preparing questions…" : "Next: answer a few questions"}</button>
            ) : (
              <div className="space-y-3">
                {questions.map((q) => (
                  <div key={q.id} className="p-3 bg-zinc-900 border border-zinc-800 rounded space-y-1.5">
                    <div className="text-xs font-medium">{q.question}</div>
                    <div className="flex flex-wrap gap-1.5">
                      {q.suggested_answers.map((a) => (
                        <button key={a} onClick={() => setAnswers((p) => ({ ...p, [q.id]: a }))} className={`px-2 py-1 rounded text-[10px] ${answers[q.id] === a ? "bg-indigo-600 text-white" : "bg-zinc-800 text-zinc-300"}`}>{a}</button>
                      ))}
                    </div>
                    <input className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-[11px]" placeholder="Or type your own answer" value={answers[q.id] ?? ""} onChange={(e) => setAnswers((p) => ({ ...p, [q.id]: e.target.value }))} />
                  </div>
                ))}
                <button disabled={modalBusy} onClick={createOfficerScenario} className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded-lg text-xs font-bold">{modalBusy ? "Checking against the evidence…" : "Build and check this theory"}</button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
