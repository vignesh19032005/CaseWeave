"use client";

import { Suspense, useEffect, useRef, useState, type ComponentType } from "react";
import { useParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { api, getToken, ApiError } from "../../lib/api";
import EntityGraph from "./EntityGraph";

const DynamicScene = dynamic(() => import("../../scene/DynamicScene"), { ssr: false });

type EvidenceItem = {
  evidence_id: string;
  filename: string;
  evidence_type: string;
  file_hash: string;
  status: string;
};

type TimelineEvent = {
  event_id: string;
  time: string;
  description: string;
  source_evidence_id: string;
  source_observation_id?: string;
  classification: string;
};

type Transcript = {
  claims: string;
  entity_context: string;
  prosecutor_argument: string;
  prosecutor_proposed_question: string;
  defender_argument: string;
  judge_relationship: string;
  judge_reason: string;
  judge_verification_question: string;
};

type Conflict = {
  conflict_id: string;
  claim_a: string;
  source_a: string;
  time_a: string;
  claim_b: string;
  source_b: string;
  time_b: string;
  question: string;
  nature_of_conflict: string;
  transcript?: Transcript;
  review_status: string;
};

type EvidenceLink = {
  link_id: string;
  claim_a: string;
  source_a: string;
  claim_b: string;
  source_b: string;
  link_type: string;
  reason: string;
  transcript?: Transcript;
};

type Entity = { entity_id: string; canonical_name: string; entity_type: string; aliases: string };
type Relationship = { from_entity_id: string; to_entity_id: string; relationship_type: string };
type Mention = { entity_id: string; observation_id: string };
type AuditEvent = { audit_id: string; actor_role: string; action: string; target: string; timestamp: string };
type ChatSource = { observation_id: string; source_evidence_id: string; extracted_time: string; text: string };
type ChatTurn = { question: string; answer: string; sources: ChatSource[] };
type UnresolvedGap = {
  question: string;
  best_guess: string | null;
  confidence: "none" | "low" | "medium" | "high";
  basis: string | null;
};
type Narrative = {
  narrative: string;
  supported_facts: string[];
  unresolved_gaps: UnresolvedGap[];
  confidence_note: string;
  provider: string;
};

const GAP_CONFIDENCE_COLORS: Record<string, string> = {
  high: "text-emerald-400",
  medium: "text-amber-400",
  low: "text-orange-400",
  none: "text-zinc-600",
};

const BADGE_COLORS: Record<string, string> = {
  observed: "bg-emerald-700",
  reported: "bg-indigo-700",
  inferred: "bg-amber-700",
  unknown: "bg-gray-600",
};

const LINK_COLORS: Record<string, string> = {
  supports: "border-emerald-700 text-emerald-400",
  related_to: "border-sky-700 text-sky-400",
};

type Tab = "evidence" | "studio" | "conflicts" | "report";

// Next.js 16: useParams() in a Client Component blocks prerendering unless
// wrapped in Suspense — this page is fully dynamic (auth-gated, per-case
// data) anyway, so the fallback is never user-visible in practice.
export default function CaseStudioPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-zinc-950" />}>
      <CaseStudio />
    </Suspense>
  );
}

function CaseStudio() {
  const { caseId } = useParams<{ caseId: string }>();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("studio");

  const [title, setTitle] = useState("");
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [evidenceLinks, setEvidenceLinks] = useState<EvidenceLink[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [relationships, setRelationships] = useState<Relationship[]>([]);
  const [mentions, setMentions] = useState<Mention[]>([]);
  const [auditStatus, setAuditStatus] = useState("");
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [error, setError] = useState("");

  const [legalQuery, setLegalQuery] = useState("");
  const [processing, setProcessing] = useState(false);
  const [jobMessage, setJobMessage] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedConflictId, setSelectedConflictId] = useState<string | null>(null);

  const DEFAULT_SCENE_DESC = "describe the room/location, door(s), and any objects or evidence visible — generate scene auto-fills this once evidence is uploaded";
  // null = not yet hand-edited, so the description below is derived from
  // evidence/timeline at render time rather than synced via an effect.
  const [manualSceneDesc, setManualSceneDesc] = useState<string | null>(null);
  const sceneDescAuto = manualSceneDesc === null;
  const sceneDesc = manualSceneDesc ?? (() => {
    const imageNames = evidence
      .filter((e) => e.evidence_type === "image")
      .map((e) => e.filename.replace(/\.[a-z0-9]+$/i, "").replace(/[_-]+/g, " "));
    const sampleEvents = timeline.slice(0, 4).map((e) => e.description);
    const parts = [...imageNames, ...sampleEvents].filter(Boolean);
    return parts.length > 0 ? parts.join("; ") : DEFAULT_SCENE_DESC;
  })();
  const [sceneDims, setSceneDims] = useState({ width_m: 10, length_m: 14, height_m: 4 });
  const [sceneJsx, setSceneJsx] = useState<string | null>(null);
  const [sceneBusy, setSceneBusy] = useState(false);

  const [question, setQuestion] = useState("");
  const [chatHistory, setChatHistory] = useState<ChatTurn[]>([]);
  const [chatBusy, setChatBusy] = useState(false);

  const [reportText, setReportText] = useState<string | null>(null);

  const [narrative, setNarrative] = useState<Narrative | null>(null);
  const [narrativeBusy, setNarrativeBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    loadAll();
    return () => stopPolling();
  }, [caseId]);

  async function loadAll() {
    setError("");
    try {
      const c = await api.getCase(caseId);
      setTitle(c.case.title);
      setEvidence(c.evidence);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load case");
      return;
    }
    refreshDerived();
  }

  async function refreshDerived() {
    try {
      const [tl, cf, links, ent, audit] = await Promise.all([
        api.getTimeline(caseId).catch(() => []),
        api.getConflicts(caseId).catch(() => []),
        api.getEvidenceLinks(caseId).catch(() => []),
        api.getEntities(caseId).catch(() => ({ entities: [], relationships: [], mentions: [] })),
        api.getAudit(caseId).catch(() => ({ chain_integrity: "", events: [] })),
      ]);
      setTimeline(tl);
      setConflicts(cf);
      setEvidenceLinks(links);
      setEntities(ent.entities);
      setRelationships(ent.relationships);
      setMentions(ent.mentions ?? []);
      setAuditStatus(audit.chain_integrity);
      setAuditEvents(audit.events ?? []);
    } catch {
      // best-effort — individual fetches already swallow their own errors
    }
  }

  async function refreshEvidence() {
    const list = await api.listEvidence(caseId);
    setEvidence(list);
  }

  async function handleUpload(files: FileList | null) {
    if (!files) return;
    setError("");
    try {
      for (const file of Array.from(files)) {
        await api.uploadEvidence(caseId, file);
      }
      await refreshEvidence();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed");
    }
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function processCase() {
    if (processing) return;
    setError("");
    setProcessing(true);
    setJobMessage("Queued...");
    stopPolling();
    const startedAt = Date.now();
    try {
      const { job_id } = await api.processCase(caseId, legalQuery || undefined);
      pollRef.current = setInterval(async () => {
        try {
          const status = await api.processStatus(caseId, job_id);
          const elapsed = Math.round((Date.now() - startedAt) / 1000);
          if (status.status === "finished") {
            stopPolling();
            setProcessing(false);
            setJobMessage(`Finished in ${elapsed}s.`);
            setNarrative(status.result?.reconstruction ?? null);
            await refreshDerived();
          } else if (status.status === "failed" || status.status === "stopped" || status.status === "canceled") {
            stopPolling();
            setProcessing(false);
            setJobMessage(`Failed: ${status.error || status.status}`);
          } else if (status.status === "not_found") {
            // Job record expired from Redis — load whatever the run persisted.
            stopPolling();
            setProcessing(false);
            setJobMessage("Job record expired — showing latest saved results.");
            await refreshDerived();
          } else {
            setJobMessage(`Running (${status.status}) — ${elapsed}s elapsed. A full run takes ~10 min.`);
          }
        } catch {
          // transient poll failure — keep polling
        }
      }, 4000);
    } catch (e) {
      setProcessing(false);
      setJobMessage("");
      setError(e instanceof ApiError ? e.message : "Could not start processing");
    }
  }

  async function generateNarrative() {
    setNarrativeBusy(true);
    setError("");
    try {
      setNarrative(await api.reconstruct(caseId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Reconstruction failed");
    } finally {
      setNarrativeBusy(false);
    }
  }

  async function reviewConflict(conflictId: string, status: string) {
    const reason = prompt(`Why are you marking this conflict "${status}"? (required, kept as an audit record)`);
    if (reason === null) return; // cancelled
    if (!reason.trim()) {
      setError("A reason is required to change a conflict's review status.");
      return;
    }
    try {
      await api.reviewConflict(caseId, conflictId, status, reason.trim());
      setConflicts((prev) => prev.map((c) => (c.conflict_id === conflictId ? { ...c, review_status: status } : c)));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update review status");
    }
  }

  async function generateScene() {
    setSceneBusy(true);
    setError("");
    try {
      const result = await api.generateScene(caseId, sceneDesc, sceneDims.width_m, sceneDims.length_m, sceneDims.height_m);
      setSceneJsx(result.jsx);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Scene generation failed");
    } finally {
      setSceneBusy(false);
    }
  }

  async function askQuestion() {
    const q = question.trim();
    if (!q || chatBusy) return;
    setChatBusy(true);
    setError("");
    setQuestion("");
    try {
      const result = await api.askCase(
        caseId,
        q,
        chatHistory.map((t) => ({ question: t.question, answer: t.answer }))
      );
      setChatHistory((prev) => [...prev, { question: q, answer: result.answer, sources: result.sources }]);
    } catch (e) {
      setQuestion(q); // let them retry without retyping
      setError(e instanceof ApiError ? e.message : "Chat failed");
    } finally {
      setChatBusy(false);
    }
  }

  async function viewReport() {
    try {
      const text = await api.getReport(caseId);
      setReportText(text);
      setTab("report");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No report yet — run the pipeline first");
    }
  }

  // --- derived linkage: which claims (source+time key) are in a conflict ---
  const conflictKeys = new Set(
    conflicts.flatMap((c) => [`${c.source_a}|${c.time_a}`, `${c.source_b}|${c.time_b}`])
  );
  const selectedEvent = timeline.find((e) => e.event_id === selectedEventId) || null;
  const relatedConflicts = selectedEvent
    ? conflicts.filter(
        (c) =>
          (c.source_a === selectedEvent.source_evidence_id && c.time_a === selectedEvent.time) ||
          (c.source_b === selectedEvent.source_evidence_id && c.time_b === selectedEvent.time)
      )
    : [];
  const relatedLinks = selectedEvent
    ? evidenceLinks.filter(
        (l) => l.source_a === selectedEvent.source_evidence_id || l.source_b === selectedEvent.source_evidence_id
      )
    : [];
  const selectedConflict = conflicts.find((c) => c.conflict_id === selectedConflictId) || null;
  const highlightedEntityIds = new Set(
    selectedEvent ? mentions.filter((m) => m.observation_id === selectedEvent.source_observation_id).map((m) => m.entity_id) : []
  );

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="border-b border-zinc-900 px-6 py-4 flex items-center justify-between">
        <div>
          <button onClick={() => router.push("/")} className="text-xs text-zinc-500 hover:text-zinc-300 mb-1">
            ← Case Command Center
          </button>
          <h1 className="text-lg font-semibold">{title || caseId}</h1>
          <div className="flex items-center gap-2 text-xs text-zinc-500 mt-1">
            <code className="bg-zinc-900 px-1.5 py-0.5 rounded">{caseId}</code>
            {auditStatus && (
              <span className={`px-1.5 py-0.5 rounded ${auditStatus === "PASSED" ? "bg-emerald-800" : "bg-red-800"}`}>
                audit chain: {auditStatus}
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-6 text-center">
          <Stat label="Evidence items" value={evidence.length} />
          <Stat label="Events extracted" value={timeline.length} />
          <Stat label="Open conflicts" value={conflicts.filter((c) => c.review_status !== "resolved").length} />
        </div>
      </div>

      {error && (
        <div className="m-6 p-3 rounded border border-red-800 bg-red-950 text-red-300 text-sm">{error}</div>
      )}

      <div className="flex gap-1 px-6 pt-4 border-b border-zinc-900">
        {(["evidence", "studio", "conflicts", "report"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm rounded-t-lg ${
              tab === t ? "bg-zinc-900 text-white border border-zinc-800 border-b-0" : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {t === "evidence" && "Evidence Explorer"}
            {t === "studio" && "Incident Reconstruction Studio"}
            {t === "conflicts" && `Conflict Analysis (${conflicts.length})`}
            {t === "report" && "Report"}
          </button>
        ))}
      </div>

      <div className="p-6">
        {tab === "evidence" && (
          <EvidenceExplorer
            caseId={caseId}
            evidence={evidence}
            auditEvents={auditEvents}
            onUpload={handleUpload}
            legalQuery={legalQuery}
            setLegalQuery={setLegalQuery}
            onProcess={processCase}
            processing={processing}
            jobMessage={jobMessage}
          />
        )}

        {tab === "studio" && (
          <StudioTab
            timeline={timeline}
            conflictKeys={conflictKeys}
            selectedEventId={selectedEventId}
            setSelectedEventId={setSelectedEventId}
            selectedEvent={selectedEvent}
            relatedConflicts={relatedConflicts}
            relatedLinks={relatedLinks}
            entities={entities}
            relationships={relationships}
            highlightedEntityIds={highlightedEntityIds}
            sceneDesc={sceneDesc}
            sceneDescAuto={sceneDescAuto}
            setSceneDesc={setManualSceneDesc}
            sceneDims={sceneDims}
            setSceneDims={setSceneDims}
            sceneJsx={sceneJsx}
            sceneBusy={sceneBusy}
            onGenerateScene={generateScene}
            DynamicScene={DynamicScene}
            question={question}
            setQuestion={setQuestion}
            chatHistory={chatHistory}
            chatBusy={chatBusy}
            onAsk={askQuestion}
            onNewConversation={() => setChatHistory([])}
            narrative={narrative}
            narrativeBusy={narrativeBusy}
            onGenerateNarrative={generateNarrative}
            onJumpToConflict={(id: string) => {
              setSelectedConflictId(id);
              setTab("conflicts");
            }}
          />
        )}

        {tab === "conflicts" && (
          <ConflictsTab
            caseId={caseId}
            conflicts={conflicts}
            evidenceLinks={evidenceLinks}
            selectedConflictId={selectedConflictId}
            setSelectedConflictId={setSelectedConflictId}
            selectedConflict={selectedConflict}
            onReview={reviewConflict}
          />
        )}

        {tab === "report" && (
          <ReportTab caseId={caseId} reportText={reportText} onLoad={viewReport} />
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      <div className="text-[11px] text-zinc-500 uppercase tracking-wide">{label}</div>
    </div>
  );
}

function EvidenceExplorer({
  caseId,
  evidence,
  auditEvents,
  onUpload,
  legalQuery,
  setLegalQuery,
  onProcess,
  processing,
  jobMessage,
}: {
  caseId: string;
  evidence: EvidenceItem[];
  auditEvents: AuditEvent[];
  onUpload: (files: FileList | null) => void;
  legalQuery: string;
  setLegalQuery: (v: string) => void;
  onProcess: () => void;
  processing: boolean;
  jobMessage: string;
}) {
  const images = evidence.filter((e) => e.evidence_type === "image");
  const other = evidence.filter((e) => e.evidence_type !== "image");
  const [custodyFor, setCustodyFor] = useState<string | null>(null);
  const [certBusy, setCertBusy] = useState<string | null>(null);
  const [certError, setCertError] = useState("");

  async function downloadCertificate(evidenceId: string) {
    setCertBusy(evidenceId);
    setCertError("");
    try {
      await api.downloadEvidenceCertificate(caseId, evidenceId);
    } catch (e) {
      setCertError(e instanceof ApiError ? e.message : "Could not generate certificate");
    } finally {
      setCertBusy(null);
    }
  }

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="border border-zinc-800 rounded-lg p-4">
          <h2 className="text-sm uppercase tracking-wide text-zinc-500 mb-3">Evidence ({evidence.length})</h2>
          <input
            type="file"
            multiple
            className="text-xs mb-3"
            onChange={(e) => {
              onUpload(e.target.files);
              e.target.value = ""; // allow re-selecting the same file
            }}
          />
          <div className="space-y-1 max-h-60 overflow-y-auto pr-2">
            {other.map((e) => (
              <div key={e.evidence_id} className="text-xs flex justify-between border-b border-zinc-900 py-1.5">
                <span>{e.filename}</span>
                <span className="text-zinc-500">{e.evidence_type}</span>
              </div>
            ))}
            {evidence.length === 0 && <div className="text-xs text-zinc-600">No evidence uploaded yet.</div>}
          </div>
        </div>

        <div className="border border-zinc-800 rounded-lg p-4">
          <h2 className="text-sm uppercase tracking-wide text-zinc-500 mb-3">Run analysis</h2>
          <input
            className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm mb-3"
            placeholder="Legal question (optional), e.g. admissibility of electronic evidence"
            value={legalQuery}
            onChange={(e) => setLegalQuery(e.target.value)}
          />
          <button
            className="bg-emerald-700 hover:bg-emerald-600 rounded px-4 py-2 text-sm font-medium disabled:opacity-50"
            onClick={onProcess}
            disabled={processing || evidence.length === 0}
          >
            {processing ? "Processing..." : "Run pipeline"}
          </button>
          {jobMessage && <div className="text-xs text-zinc-500 mt-3">{jobMessage}</div>}
          <p className="text-[11px] text-zinc-600 mt-4">
            Extracts observations from every evidence item — text documents, logs, PDFs, photos (vision-described),
            audio and video (transcribed) — builds the timeline, resolves entities, runs the 3-agent discrepancy
            debate, and generates one combined reconstruction + report (~10-20 min depending on evidence count).
            Re-running replaces previous results, including conflict review statuses. Requires the worker process
            (`python worker.py`) running.
          </p>
        </div>
      </div>

      <WitnessStatementForm onUpload={onUpload} />

      {images.length > 0 && (
        <div className="border border-zinc-800 rounded-lg p-4">
          <h2 className="text-sm uppercase tracking-wide text-zinc-500 mb-1">Photo evidence ({images.length})</h2>
          <p className="text-[11px] text-zinc-600 mb-4">
            Each photo is vision-described during pipeline processing and folded into the single combined
            reconstruction in the Studio tab — no per-photo action needed here.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {images.map((img) => (
              <div key={img.evidence_id} className="border border-zinc-900 rounded-lg p-2">
                <EvidenceImage caseId={caseId} evidenceId={img.evidence_id} alt={img.filename} />
                <div className="text-[11px] text-zinc-400 truncate mt-1">{img.filename}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {evidence.length > 0 && (
        <div className="border border-zinc-800 rounded-lg p-4">
          <h2 className="text-sm uppercase tracking-wide text-zinc-500 mb-1">Chain of custody</h2>
          <p className="text-[11px] text-zinc-600 mb-3">
            Every evidence item is hash-verified on upload and every action against it is appended to a
            hash-chained audit log — click an item to see its full history.
          </p>
          {certError && (
            <div className="mb-3 p-2 rounded border border-red-800 bg-red-950 text-red-300 text-xs">{certError}</div>
          )}
          <div className="space-y-1 max-h-72 overflow-y-auto pr-2">
            {evidence.map((e) => {
              const itemEvents = auditEvents
                .filter((a) => a.target === e.evidence_id)
                .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
              const open = custodyFor === e.evidence_id;
              return (
                <div key={e.evidence_id} className="border-b border-zinc-900 py-1.5">
                  <button
                    onClick={() => setCustodyFor(open ? null : e.evidence_id)}
                    className="w-full flex items-center justify-between text-xs hover:text-zinc-300"
                  >
                    <span className="truncate">{e.filename}</span>
                    <span className="text-zinc-600 shrink-0 ml-2">
                      {itemEvents.length} event{itemEvents.length === 1 ? "" : "s"} {open ? "▲" : "▼"}
                    </span>
                  </button>
                  {open && (
                    <div className="mt-2 space-y-1.5 text-[11px]">
                      <div className="text-zinc-500">
                        SHA-256: <span className="text-zinc-400">{e.file_hash}</span>
                      </div>
                      <div className="text-zinc-500">
                        Evidence ID: <span className="text-zinc-400">{e.evidence_id}</span>
                      </div>
                      <button
                        onClick={() => downloadCertificate(e.evidence_id)}
                        disabled={certBusy === e.evidence_id}
                        className="text-indigo-400 hover:text-indigo-300 disabled:opacity-50 underline"
                      >
                        {certBusy === e.evidence_id ? "Preparing..." : "Download draft electronic-evidence certificate (PDF)"}
                      </button>
                      {itemEvents.length === 0 ? (
                        <div className="text-zinc-600 italic">No recorded events for this item yet.</div>
                      ) : (
                        itemEvents.map((ev) => (
                          <div key={ev.audit_id} className="border-l-2 border-zinc-800 pl-2">
                            <span className="text-zinc-300">{ev.action.replace(/_/g, " ")}</span>{" "}
                            <span className="text-zinc-600">
                              by {ev.actor_role} · {new Date(ev.timestamp + "Z").toLocaleString()}
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function WitnessStatementForm({ onUpload }: { onUpload: (files: FileList | null) => void }) {
  const blank = { name: "", role: "", date: "", time: "", location: "", contact: "", statement: "" };
  const [fields, setFields] = useState(blank);
  const [open, setOpen] = useState(false);

  function set<K extends keyof typeof blank>(key: K, value: string) {
    setFields((f) => ({ ...f, [key]: value }));
  }

  function submit() {
    if (!fields.name.trim() || !fields.statement.trim()) return;
    const lines = [
      "WITNESS STATEMENT",
      "",
      `Witness name: ${fields.name.trim()}`,
      `Role / relationship to case: ${fields.role.trim() || "(not stated)"}`,
      `Date of observation: ${fields.date || "(not stated)"}`,
      `Time of observation: ${fields.time || "(not stated)"}`,
      `Location of observation: ${fields.location.trim() || "(not stated)"}`,
      `Contact: ${fields.contact.trim() || "(not provided)"}`,
      `Statement recorded: ${new Date().toISOString()}`,
      "",
      "Statement:",
      fields.statement.trim(),
    ];
    const content = lines.join("\n");
    const safeName = fields.name.trim().replace(/[^a-z0-9]+/gi, "_").toLowerCase();
    const file = new File([content], `witness_statement_${safeName || "unnamed"}_${Date.now()}.txt`, { type: "text/plain" });
    // DataTransfer is the standard way to build a real FileList in the browser.
    const dt = new DataTransfer();
    dt.items.add(file);
    onUpload(dt.files);
    setFields(blank);
    setOpen(false);
  }

  return (
    <div className="border border-zinc-800 rounded-lg p-4">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between text-sm uppercase tracking-wide text-zinc-500"
      >
        <span>Add witness statement (guided form)</span>
        <span>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="mt-4 space-y-3">
          <p className="text-[11px] text-zinc-600">
            Fields are formatted into a labeled text document and uploaded as evidence — same pipeline as any
            other file, just guided instead of free-text.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input
              className="bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm"
              placeholder="Witness name *"
              value={fields.name}
              onChange={(e) => set("name", e.target.value)}
            />
            <input
              className="bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm"
              placeholder="Role / relationship to case"
              value={fields.role}
              onChange={(e) => set("role", e.target.value)}
            />
            <input
              type="date"
              className="bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm"
              value={fields.date}
              onChange={(e) => set("date", e.target.value)}
            />
            <input
              type="time"
              className="bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm"
              value={fields.time}
              onChange={(e) => set("time", e.target.value)}
            />
            <input
              className="bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm"
              placeholder="Location of observation"
              value={fields.location}
              onChange={(e) => set("location", e.target.value)}
            />
            <input
              className="bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm"
              placeholder="Contact (optional)"
              value={fields.contact}
              onChange={(e) => set("contact", e.target.value)}
            />
          </div>
          <textarea
            className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm"
            rows={4}
            placeholder="Statement, in the witness's own words *"
            value={fields.statement}
            onChange={(e) => set("statement", e.target.value)}
          />
          <button
            onClick={submit}
            disabled={!fields.name.trim() || !fields.statement.trim()}
            className="bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 rounded px-4 py-2 text-sm font-medium"
          >
            Add as evidence
          </button>
        </div>
      )}
    </div>
  );
}

function EvidenceImage({ caseId, evidenceId, alt }: { caseId: string; evidenceId: string; alt: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    api
      .evidenceFileUrl(caseId, evidenceId)
      .then((u) => {
        objectUrl = u;
        if (cancelled) URL.revokeObjectURL(u);
        else setUrl(u);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [caseId, evidenceId]);

  if (failed) {
    return (
      <div className="w-full h-48 rounded mb-2 bg-zinc-900 flex items-center justify-center text-xs text-red-400">
        Could not load image
      </div>
    );
  }
  return url ? (
    <img src={url} alt={alt} className="w-full h-48 object-cover rounded mb-2 bg-zinc-900" />
  ) : (
    <div className="w-full h-48 rounded mb-2 bg-zinc-900 animate-pulse" />
  );
}

type SceneComponent = ComponentType<{ jsx: string }>;
type SceneDims = { width_m: number; length_m: number; height_m: number };

type StudioTabProps = {
  timeline: TimelineEvent[];
  conflictKeys: Set<string>;
  selectedEventId: string | null;
  setSelectedEventId: (id: string | null) => void;
  selectedEvent: TimelineEvent | null;
  relatedConflicts: Conflict[];
  relatedLinks: EvidenceLink[];
  entities: Entity[];
  relationships: Relationship[];
  highlightedEntityIds: Set<string>;
  sceneDesc: string;
  sceneDescAuto: boolean;
  setSceneDesc: (v: string) => void;
  sceneDims: SceneDims;
  setSceneDims: (d: SceneDims) => void;
  sceneJsx: string | null;
  sceneBusy: boolean;
  onGenerateScene: () => void;
  DynamicScene: SceneComponent;
  question: string;
  setQuestion: (v: string) => void;
  chatHistory: ChatTurn[];
  chatBusy: boolean;
  onAsk: () => void;
  onNewConversation: () => void;
  narrative: Narrative | null;
  narrativeBusy: boolean;
  onGenerateNarrative: () => void;
  onJumpToConflict: (id: string) => void;
};

function StudioTab(props: StudioTabProps) {
  const {
    timeline,
    conflictKeys,
    selectedEventId,
    setSelectedEventId,
    selectedEvent,
    relatedConflicts,
    relatedLinks,
    entities,
    relationships,
    highlightedEntityIds,
    sceneDesc,
    sceneDescAuto,
    setSceneDesc,
    sceneDims,
    setSceneDims,
    sceneJsx,
    sceneBusy,
    onGenerateScene,
    DynamicScene,
    question,
    setQuestion,
    chatHistory,
    chatBusy,
    onAsk,
    onNewConversation,
    narrative,
    narrativeBusy,
    onGenerateNarrative,
    onJumpToConflict,
  } = props;

  const selectedPanelRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (selectedEventId) {
      selectedPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [selectedEventId]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-6">
      <div className="space-y-6">
        <div className="border border-zinc-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-sm uppercase tracking-wide text-zinc-500">Reconstructed sequence</h2>
            <button
              className="bg-indigo-600 hover:bg-indigo-500 rounded px-3 py-1.5 text-xs font-medium disabled:opacity-50"
              onClick={onGenerateNarrative}
              disabled={narrativeBusy || timeline.length === 0}
            >
              {narrativeBusy ? "Synthesizing..." : narrative ? "Regenerate" : "Generate reconstruction"}
            </button>
          </div>
          <p className="text-[11px] text-zinc-600 mb-3">
            One narrative across timeline, entities, conflicts and evidence links — gaps are flagged, not smoothed over.
          </p>
          {narrative ? (
            <div className="space-y-3 text-xs">
              <p className="text-sm text-zinc-200 leading-relaxed">{narrative.narrative}</p>
              {narrative.supported_facts?.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase text-emerald-400 mb-1">Supported by evidence</div>
                  <ul className="list-disc pl-5 space-y-0.5 text-zinc-300">
                    {narrative.supported_facts.map((f, i) => <li key={i}>{f}</li>)}
                  </ul>
                </div>
              )}
              {narrative.unresolved_gaps?.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase text-amber-400 mb-1">Unresolved gaps</div>
                  <div className="space-y-2">
                    {narrative.unresolved_gaps.map((g, i) => (
                      <div key={i} className="border-l-2 border-amber-900 pl-2">
                        <div className="text-zinc-300">{g.question}</div>
                        {g.best_guess ? (
                          <div className="text-zinc-500 mt-0.5">
                            Possible answer{" "}
                            <span className={`uppercase ${GAP_CONFIDENCE_COLORS[g.confidence]}`}>
                              (unverified, {g.confidence} confidence)
                            </span>
                            : {g.best_guess}
                            {g.basis && <span className="text-zinc-600"> — basis: {g.basis}</span>}
                          </div>
                        ) : (
                          <div className="text-zinc-600 mt-0.5 italic">No basis in the evidence for a guess.</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {narrative.confidence_note && <div className="text-zinc-500 italic">{narrative.confidence_note}</div>}
              <div className="text-[10px] text-zinc-600">via {narrative.provider}</div>
            </div>
          ) : (
            <div className="text-xs text-zinc-600">
              {timeline.length === 0 ? "Run the pipeline first." : "Not generated yet."}
            </div>
          )}
        </div>

        <div className="border border-zinc-800 rounded-lg p-4">
          <h2 className="text-sm uppercase tracking-wide text-zinc-500 mb-1">Incident reconstruction</h2>
          <p className="text-[11px] text-zinc-600 mb-3">
            Procedural approximation of the scene — approximate geometry from vision description, not a precision
            3D reconstruction. Generate it, then select a timeline event to see linked evidence and conflicts below.
            {sceneDescAuto && " Description below is auto-filled from this case's uploaded evidence — edit it to steer the scene."}
          </p>
          <div className="flex gap-2 mb-3 flex-wrap">
            <input
              className="flex-1 min-w-[240px] bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-xs"
              value={sceneDesc}
              onChange={(e) => setSceneDesc(e.target.value)}
            />
            {(["width_m", "length_m", "height_m"] as const).map((dim) => (
              <input
                key={dim}
                type="number"
                className="w-20 bg-zinc-900 border border-zinc-800 rounded px-2 py-2 text-xs"
                value={sceneDims[dim]}
                title={dim.replace("_m", " (m)")}
                onChange={(e) => setSceneDims({ ...sceneDims, [dim]: parseFloat(e.target.value) || 0 })}
              />
            ))}
            <button
              className="bg-indigo-600 hover:bg-indigo-500 rounded px-3 py-2 text-xs font-medium disabled:opacity-50"
              onClick={onGenerateScene}
              disabled={sceneBusy}
            >
              {sceneBusy ? "Generating..." : "Generate scene"}
            </button>
          </div>
          {sceneJsx ? (
            <DynamicScene jsx={sceneJsx} />
          ) : (
            <div className="h-48 flex items-center justify-center text-xs text-zinc-600 border border-dashed border-zinc-800 rounded">
              No scene generated yet.
            </div>
          )}
        </div>

        <div className="border border-zinc-800 rounded-lg p-4">
          <h2 className="text-sm uppercase tracking-wide text-zinc-500 mb-3">Event timeline — select an event</h2>
          <div className="space-y-1.5 max-h-96 overflow-y-auto pr-2">
            {timeline.map((e) => {
              const isConflict = conflictKeys.has(`${e.source_evidence_id}|${e.time}`);
              const isSelected = e.event_id === selectedEventId;
              return (
                <button
                  key={e.event_id}
                  onClick={() => setSelectedEventId(isSelected ? null : e.event_id)}
                  className={`w-full text-left flex gap-3 pb-2 pt-1 border-b border-zinc-900 px-2 rounded ${
                    isSelected ? "bg-indigo-950/50 ring-1 ring-indigo-800" : isConflict ? "bg-red-950/20" : "hover:bg-zinc-900"
                  }`}
                >
                  <div className="w-16 shrink-0 text-xs text-zinc-500 tabular-nums pt-0.5">{e.time}</div>
                  <div className="flex-1">
                    <span
                      className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full text-white ${
                        isConflict ? "bg-red-700" : BADGE_COLORS[e.classification] || "bg-gray-600"
                      }`}
                    >
                      {isConflict ? "conflict" : e.classification}
                    </span>
                    <div className="text-sm mt-1">{e.description}</div>
                    <div className="text-[11px] text-zinc-600 mt-1">source: {e.source_evidence_id}</div>
                  </div>
                </button>
              );
            })}
            {timeline.length === 0 && (
              <div className="text-xs text-zinc-600">No timeline yet — run the pipeline from Evidence Explorer.</div>
            )}
          </div>
        </div>

        <div className="border border-zinc-800 rounded-lg p-4">
          <h2 className="text-sm uppercase tracking-wide text-zinc-500 mb-1">
            Entity &amp; relationship graph ({entities.length} entities, {relationships.length} relationships)
          </h2>
          <p className="text-[11px] text-zinc-600 mb-2">
            People, devices and places resolved across all sources (aliases merged). Selecting a timeline event rings
            the entities it mentions.
          </p>
          <EntityGraph entities={entities} relationships={relationships} highlightIds={highlightedEntityIds} />
        </div>
      </div>

      <div className="space-y-4">
        <div ref={selectedPanelRef} className="border border-zinc-800 rounded-lg p-4 scroll-mt-4">
          <h2 className="text-sm uppercase tracking-wide text-zinc-500 mb-3">
            {selectedEvent ? "Selected event — linked evidence" : "Select an event to inspect it"}
          </h2>
          {!selectedEvent && <div className="text-xs text-zinc-600">Click a timeline event on the left.</div>}
          {selectedEvent && (
            <div className="space-y-3">
              <div className="text-xs text-zinc-400">
                <span className="font-medium text-zinc-200">{selectedEvent.time}</span> — {selectedEvent.description}
              </div>
              {relatedConflicts.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase text-red-400 mb-1">Conflicts ({relatedConflicts.length})</div>
                  {relatedConflicts.map((c) => (
                    <button
                      key={c.conflict_id}
                      onClick={() => onJumpToConflict(c.conflict_id)}
                      className="w-full text-left text-xs border border-red-900 rounded p-2 mb-2 hover:bg-red-950/30"
                    >
                      {c.nature_of_conflict || c.question}
                    </button>
                  ))}
                </div>
              )}
              {relatedLinks.length > 0 && (
                <div>
                  <div className="text-[11px] uppercase text-zinc-500 mb-1">Related evidence ({relatedLinks.length})</div>
                  {relatedLinks.map((l) => (
                    <div key={l.link_id} className={`text-xs border rounded p-2 mb-2 ${LINK_COLORS[l.link_type] || "border-zinc-800"}`}>
                      <div className="uppercase text-[10px] mb-1">{l.link_type}</div>
                      {l.reason}
                    </div>
                  ))}
                </div>
              )}
              {relatedConflicts.length === 0 && relatedLinks.length === 0 && (
                <div className="text-xs text-zinc-600">No linked conflicts or evidence for this event.</div>
              )}
            </div>
          )}
        </div>


        <div className="border border-zinc-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm uppercase tracking-wide text-zinc-500">
              Ask the case {chatHistory.length > 0 && `(${chatHistory.length})`}
            </h2>
            {chatHistory.length > 0 && (
              <button onClick={onNewConversation} className="text-[11px] text-zinc-500 hover:text-zinc-300 underline">
                New conversation
              </button>
            )}
          </div>

          {chatHistory.length > 0 && (
            <div className="space-y-4 mb-3 max-h-80 overflow-y-auto pr-2">
              {chatHistory.map((turn, i) => (
                <div key={i} className="text-xs">
                  <div className="text-zinc-200 font-medium mb-1">{turn.question}</div>
                  <div className="text-zinc-400 whitespace-pre-wrap">{turn.answer}</div>
                  {turn.sources?.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {turn.sources.map((s) => (
                        <div key={s.observation_id} className="border-l-2 border-zinc-800 pl-2 text-zinc-500">
                          <span className="text-zinc-600">
                            {s.extracted_time || "—"} · {s.source_evidence_id}
                          </span>
                          <div className="text-zinc-500">{s.text}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          <textarea
            className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-xs mb-2"
            rows={2}
            placeholder={
              chatHistory.length > 0
                ? "Ask a follow-up — earlier answers in this conversation are remembered"
                : "e.g. What remains unverified about the sequence of events?"
            }
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onAsk();
              }
            }}
          />
          <button
            className="bg-indigo-600 hover:bg-indigo-500 rounded px-3 py-1.5 text-xs font-medium disabled:opacity-50"
            onClick={onAsk}
            disabled={chatBusy || !question.trim()}
          >
            {chatBusy ? "Thinking..." : "Ask"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ConflictsTab({
  caseId,
  conflicts,
  evidenceLinks,
  selectedConflictId,
  setSelectedConflictId,
  selectedConflict,
  onReview,
}: {
  caseId: string;
  conflicts: Conflict[];
  evidenceLinks: EvidenceLink[];
  selectedConflictId: string | null;
  setSelectedConflictId: (id: string | null) => void;
  selectedConflict: Conflict | null;
  onReview: (id: string, status: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
      <div className="border border-zinc-800 rounded-lg p-4">
        <h2 className="text-sm uppercase tracking-wide text-zinc-500 mb-3">Conflicts ({conflicts.length})</h2>
        <div className="space-y-2 max-h-[70vh] overflow-y-auto pr-2">
          {conflicts.map((c) => (
            <button
              key={c.conflict_id}
              onClick={() => setSelectedConflictId(c.conflict_id)}
              className={`w-full text-left text-xs border rounded p-3 ${
                selectedConflictId === c.conflict_id ? "border-red-600 bg-red-950/30" : "border-red-900 hover:bg-red-950/15"
              }`}
            >
              <div className="flex justify-between mb-1">
                <span className="text-red-400 font-medium">{c.time_a} vs {c.time_b}</span>
                <span className="text-[10px] uppercase text-zinc-500">{c.review_status}</span>
              </div>
              <div className="text-zinc-400">{c.nature_of_conflict || c.question}</div>
            </button>
          ))}
          {conflicts.length === 0 && <div className="text-xs text-zinc-600">No conflicts detected.</div>}
        </div>

        {evidenceLinks.length > 0 && (
          <>
            <h2 className="text-sm uppercase tracking-wide text-zinc-500 mt-5 mb-3">
              Supporting / related evidence ({evidenceLinks.length})
            </h2>
            <div className="space-y-2 max-h-48 overflow-y-auto pr-2">
              {evidenceLinks.map((l) => (
                <div key={l.link_id} className={`text-xs border rounded p-2 ${LINK_COLORS[l.link_type] || "border-zinc-800"}`}>
                  <div className="uppercase text-[10px] mb-1">{l.link_type}</div>
                  {l.reason}
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="border border-zinc-800 rounded-lg p-4">
        {!selectedConflict && (
          <div className="text-sm text-zinc-600">Select a conflict on the left to see the side-by-side source
            excerpts and the full Prosecutor / Defender / Judge debate transcript that produced the verdict.</div>
        )}
        {selectedConflict && (
          <div className="space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium">Conflict {selectedConflict.conflict_id}</h2>
              <div className="flex gap-2">
                {(["confirmed", "resolved", "unresolved"] as const).map((status) => (
                  <button
                    key={status}
                    onClick={() => onReview(selectedConflict.conflict_id, status)}
                    className={`text-xs px-2 py-1 rounded border ${
                      selectedConflict.review_status === status
                        ? "bg-indigo-700 border-indigo-600"
                        : "border-zinc-700 hover:bg-zinc-800"
                    }`}
                  >
                    {status}
                  </button>
                ))}
              </div>
            </div>

            <ReviewHistory caseId={caseId} conflictId={selectedConflict.conflict_id} reviewStatus={selectedConflict.review_status} />

            <div className="grid grid-cols-2 gap-4">
              <div className="border border-zinc-800 rounded p-3 text-xs">
                <div className="text-zinc-500 mb-1">Claim A — {selectedConflict.time_a} ({selectedConflict.source_a})</div>
                <div>{selectedConflict.claim_a}</div>
              </div>
              <div className="border border-zinc-800 rounded p-3 text-xs">
                <div className="text-zinc-500 mb-1">Claim B — {selectedConflict.time_b} ({selectedConflict.source_b})</div>
                <div>{selectedConflict.claim_b}</div>
              </div>
            </div>

            <div className="border border-amber-900 bg-amber-950/20 rounded p-3 text-xs">
              <div className="text-amber-400 font-medium mb-1">Recommended next step</div>
              <div className="text-zinc-300">{selectedConflict.question}</div>
              <div className="text-zinc-600 mt-1.5">
                This does not resolve the conflict — it tells you what to go check (footage, logs, a follow-up
                interview) to actually resolve it.
              </div>
            </div>

            {selectedConflict.transcript && (
              <div>
                <h3 className="text-xs uppercase text-zinc-500 mb-2">Debate transcript</h3>
                <div className="space-y-3 text-xs">
                  {selectedConflict.transcript.entity_context && (
                    <div className="text-zinc-500 italic">{selectedConflict.transcript.entity_context}</div>
                  )}
                  <div className="border-l-2 border-red-700 pl-3">
                    <div className="text-red-400 font-medium mb-1">Prosecutor</div>
                    {selectedConflict.transcript.prosecutor_argument}
                  </div>
                  <div className="border-l-2 border-sky-700 pl-3">
                    <div className="text-sky-400 font-medium mb-1">Defender</div>
                    {selectedConflict.transcript.defender_argument}
                  </div>
                  <div className="border-l-2 border-zinc-500 pl-3">
                    <div className="text-zinc-200 font-medium mb-1">
                      Judge verdict: {(selectedConflict.transcript.judge_relationship || "").toUpperCase()}
                    </div>
                    {selectedConflict.transcript.judge_reason}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

type ReviewEntry = {
  review_id: string;
  status: string;
  reason: string;
  actor_username: string;
  actor_role: string;
  timestamp: string;
};

function ReviewHistory({ caseId, conflictId, reviewStatus }: { caseId: string; conflictId: string; reviewStatus: string }) {
  const cacheKey = `${caseId}|${conflictId}|${reviewStatus}`;
  // Store which key the current data belongs to, instead of resetting to
  // null synchronously in the effect — a stale-key mismatch reads as
  // "loading" without an extra setState call at effect-start.
  const [loaded, setLoaded] = useState<{ key: string; data: ReviewEntry[] } | null>(null);
  const history = loaded?.key === cacheKey ? loaded.data : null;

  useEffect(() => {
    let cancelled = false;
    api
      .getConflictReviews(caseId, conflictId)
      .then((h) => !cancelled && setLoaded({ key: cacheKey, data: h }))
      .catch(() => !cancelled && setLoaded({ key: cacheKey, data: [] }));
    return () => {
      cancelled = true;
    };
  }, [caseId, conflictId, reviewStatus, cacheKey]);

  if (history === null) return <div className="text-[11px] text-zinc-600">Loading review history...</div>;
  if (history.length === 0) return <div className="text-[11px] text-zinc-600">No status changes recorded yet — still at the default &ldquo;unresolved&rdquo;.</div>;

  return (
    <div>
      <div className="text-[11px] uppercase text-zinc-500 mb-1">Review history</div>
      <div className="space-y-1.5">
        {history.map((r) => (
          <div key={r.review_id} className="text-xs border-l-2 border-zinc-800 pl-2">
            <span className="text-zinc-300 font-medium">{r.status}</span>{" "}
            <span className="text-zinc-600">
              by {r.actor_username} ({r.actor_role}) · {new Date(r.timestamp + "Z").toLocaleString()}
            </span>
            <div className="text-zinc-400">{r.reason}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReportTab({ caseId, reportText, onLoad }: { caseId: string; reportText: string | null; onLoad: () => void }) {
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState("");

  async function downloadPdf() {
    setPdfBusy(true);
    setPdfError("");
    try {
      await api.downloadReportPdf(caseId);
    } catch (e) {
      setPdfError(e instanceof ApiError ? e.message : "Could not download PDF");
    } finally {
      setPdfBusy(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <button className="bg-indigo-600 hover:bg-indigo-500 rounded px-4 py-2 text-sm font-medium" onClick={onLoad}>
          Load / refresh report
        </button>
        <button
          className="bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 rounded px-4 py-2 text-sm font-medium"
          onClick={downloadPdf}
          disabled={pdfBusy}
        >
          {pdfBusy ? "Preparing PDF..." : "Download formatted PDF"}
        </button>
        <span className="text-xs text-zinc-600">Requires the pipeline to have run at least once.</span>
      </div>
      {pdfError && (
        <div className="mb-4 p-3 rounded border border-red-800 bg-red-950 text-red-300 text-sm">{pdfError}</div>
      )}
      {reportText ? (
        <pre className="whitespace-pre-wrap text-xs border border-zinc-800 rounded-lg p-4 bg-zinc-900/40">
          {reportText}
        </pre>
      ) : (
        <div className="text-sm text-zinc-600">No report loaded yet — use Load/refresh for the raw text view, or
          Download formatted PDF for a formatted document.</div>
      )}
    </div>
  );
}
