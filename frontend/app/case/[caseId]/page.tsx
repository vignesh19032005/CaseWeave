"use client";
import Markdown from "../../lib/Markdown";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { api, getToken, ApiError } from "../../lib/api";
import EntityGraph from "./EntityGraph";

<<<<<<< HEAD
const DynamicScene = dynamic(() => import("../../scene/DynamicScene"), { ssr: false });
const SimulationPlayer = dynamic(() => import("../../scene/SimulationPlayer"), { ssr: false });
=======
const ForensicSandboxPlayer = dynamic(() => import("../../scene/ForensicSandboxPlayer"), { ssr: false });
>>>>>>> feature/investigative-sandbox

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
type ChatTurn = { question: string; answer: string | null; sources: ChatSource[]; error?: string };
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


type SegmentMatch = {
  label?: string;
  color?: string;
  box?: { pct_left: number; pct_top: number; pct_width: number; pct_height: number };
};
type SegmentResult = { matches: SegmentMatch[]; detected_count?: number; failed_terms?: string[] };

type PatternSignature = {
  crime_category?: string;
  point_of_entry?: string;
  tools_used?: string;
  target_goods?: string;
  timing_window?: string;
  mo_summary?: string;
  signature_traits?: string[];
};
type SimilarCase = PatternSignature & {
  case_id: string;
  is_synthetic_reference?: boolean;
  title?: string;
  jurisdiction?: string;
  fir_number?: string;
  fir_date?: string;
  similarity_percentage: number;
};
type PatternSynthesis = {
  note?: string;
  compared_with?: string;
  verdict?: string;
  matching_traits?: string[];
  divergent_factors?: string[];
  inter_station_leads?: string[];
};
type PatternsData = {
  status?: "ok" | "unavailable";
  reason?: string;
  cached?: boolean;
  active_signature?: PatternSignature;
  similar_cases?: SimilarCase[];
  comparative_synthesis?: PatternSynthesis | null;
};

type RecommendedSection = {
  act?: string;
  section?: string;
  title?: string;
  cognizable?: boolean;
  bailable?: boolean;
  punishment?: string;
  triable_by?: string;
  details_source?: string | null;
  justification?: string;
  statutory_ingredients_met?: string[];
};
type ComplianceItem = {
  rule?: string;
  statute?: string;
  status?: string;
  verdict?: string;
  details?: string;
  severity?: string;
  statutory_form?: string;
};
type LegalAdvisory = {
  status?: "ok" | "unavailable";
  reason?: string;
  notice?: string;
  advisory?: {
    recommended_sections?: RecommendedSection[];
    accused_demographic_assessment?: { is_juvenile?: boolean | null; age_assessed?: string; applicable_regime?: string };
    evidentiary_safeguards?: unknown[];
    source?: string;
    notice?: string;
  };
  compliance_audit?: { compliance_items?: ComplianceItem[] };
};
type LegalDoc = {
  id: string;
  verification_status?: string;
  practice_note?: string;
  act?: string;
  section?: string;
  title: string;
  text?: string;
  cognizable?: boolean | null;
  punishment?: string;
  ingredients?: string[];
};

type Tab = "evidence" | "studio" | "conflicts" | "patterns" | "legal" | "report";

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
  const [question, setQuestion] = useState("");
  const [chatHistory, setChatHistory] = useState<ChatTurn[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  // the conversation is kept across page reloads (per case, in this browser only); it is restored when the case loads
  useEffect(() => {
    try {
      const done = chatHistory.filter((t) => t.answer);
      if (done.length) window.localStorage.setItem(`cw_chat_${caseId}`, JSON.stringify(done));
    } catch {
      // storage unavailable: the conversation just is not remembered
    }
  }, [chatHistory, caseId]);

  const [reportText, setReportText] = useState<string | null>(null);

  const [narrative, setNarrative] = useState<Narrative | null>(null);
  const [narrativeBusy, setNarrativeBusy] = useState(false);

  const restoreChat = useCallback(() => {
    try {
      const raw = window.localStorage.getItem(`cw_chat_${caseId}`);
      const saved = raw ? (JSON.parse(raw) as ChatTurn[]) : [];
      if (Array.isArray(saved) && saved.length) setChatHistory((prev) => (prev.length ? prev : saved.filter((t) => t && typeof t.question === "string" && t.answer)));
    } catch {
      // storage unavailable: start empty
    }
  }, [caseId]);

  const refreshDerived = useCallback(async () => {
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
      // the saved incident narrative (so a reload does not lose it)
      api.getNarrative(caseId).then((n: { content?: Narrative | null }) => { if (n?.content) setNarrative((cur) => cur ?? n.content ?? null); }).catch(() => undefined);
    } catch {
      // best-effort — individual fetches already swallow their own errors
    }
  }, [caseId]);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    let alive = true;
    api
      .getCase(caseId)
      .then((c) => {
        if (!alive) return;
        setError("");
        setTitle(c.case.title);
        setEvidence(c.evidence);
        restoreChat();
        refreshDerived();
      })
      .catch((e) => {
        if (alive) setError(e instanceof ApiError ? e.message : "Could not load case");
      });
    return () => {
      alive = false;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [caseId, router, restoreChat, refreshDerived]);

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
      let inFlight = false;
      pollRef.current = setInterval(async () => {
        if (inFlight) return; // a slow status call must not stack up behind itself
        inFlight = true;
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
        } finally {
          inFlight = false;
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

  async function askQuestion() {
    const q = question.trim();
    if (!q || chatBusy) return;
    setChatBusy(true);
    setError("");
    setQuestion("");
    // earlier answered turns are remembered by the model; the new question shows at once as a message of its own
    const earlier = chatHistory.filter((t) => t.answer).map((t) => ({ question: t.question, answer: t.answer as string }));
    setChatHistory((prev) => [...prev.filter((t) => !t.error), { question: q, answer: null, sources: [] }]);
    try {
      const result = await api.askCase(caseId, q, earlier);
      setChatHistory((prev) => prev.map((t, i) => (i === prev.length - 1 ? { question: q, answer: result.answer, sources: result.sources } : t)));
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "The answer could not be produced. Try again.";
      setChatHistory((prev) => prev.map((t, i) => (i === prev.length - 1 ? { question: q, answer: null, sources: [], error: msg } : t)));
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
        {(["evidence", "studio", "conflicts", "patterns", "legal", "report"] as Tab[]).map((t) => (
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
            {t === "patterns" && "Pattern Intelligence"}
            {t === "legal" && "Legal references (AI draft)"}
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
            caseId={caseId}
            SimulationPlayer={SimulationPlayer}
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
            question={question}
            setQuestion={setQuestion}
            chatHistory={chatHistory}
            chatBusy={chatBusy}
            onAsk={askQuestion}
            onNewConversation={() => {
              setChatHistory([]);
              try {
                window.localStorage.removeItem(`cw_chat_${caseId}`);
              } catch {
                // nothing stored to clear
              }
            }}
            narrative={narrative}
            narrativeBusy={narrativeBusy}
            onGenerateNarrative={generateNarrative}
            onJumpToConflict={(id: string) => {
              setSelectedConflictId(id);
              setTab("conflicts");
            }}
            caseId={caseId}
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

        {tab === "patterns" && (
          <PatternsTab caseId={caseId} />
        )}

        {tab === "legal" && (
          <LegalTab caseId={caseId} />
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
  const [segmentingId, setSegmentingId] = useState<string | null>(null);
  const [segmentPrompt, setSegmentPrompt] = useState<Record<string, string>>({});
  const [segmentResults, setSegmentResults] = useState<Record<string, SegmentResult>>({});
  const [segmentError, setSegmentError] = useState<Record<string, string>>({});

  async function handleSegment(evidenceId: string) {
    const prompt = segmentPrompt[evidenceId]?.trim();
    if (!prompt) return;
    setSegmentingId(evidenceId);
    setSegmentError((prev) => ({ ...prev, [evidenceId]: "" }));
    try {
      const res = await api.segmentEvidence(caseId, evidenceId, prompt);
      setSegmentResults((prev) => ({ ...prev, [evidenceId]: res }));
    } catch (e) {
      setSegmentError((prev) => ({
        ...prev,
        [evidenceId]: e instanceof ApiError ? e.message : "Segmentation request failed",
      }));
    } finally {
      setSegmentingId(null);
    }
  }

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
    <div className="space-y-6">
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
              <div key={img.evidence_id} className="border border-zinc-900 rounded-lg p-2.5 flex flex-col justify-between">
                <div>
                  <EvidenceImage
                    caseId={caseId}
                    evidenceId={img.evidence_id}
                    alt={img.filename}
                    matches={segmentResults[img.evidence_id]?.matches || []}
                  />
                  <div className="text-[11px] text-zinc-400 truncate mt-1.5 font-medium">{img.filename}</div>
                </div>

                <div className="mt-3 pt-2 border-t border-zinc-900/80">
                  <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">SAM 3.1 Segment</div>
                  <div className="flex gap-1.5">
                    <input
                      type="text"
                      placeholder="e.g. glove, crowbar, padlock"
                      value={segmentPrompt[img.evidence_id] || ""}
                      onChange={(e) =>
                        setSegmentPrompt((prev) => ({ ...prev, [img.evidence_id]: e.target.value }))
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleSegment(img.evidence_id);
                      }}
                      className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-[11px] w-full focus:outline-none focus:border-indigo-500"
                    />
                    <button
                      onClick={() => handleSegment(img.evidence_id)}
                      disabled={segmentingId === img.evidence_id || !segmentPrompt[img.evidence_id]?.trim()}
                      className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white px-2 py-1 rounded text-[11px] font-medium shrink-0"
                    >
                      {segmentingId === img.evidence_id ? "..." : "Segment"}
                    </button>
                  </div>
                  {segmentError[img.evidence_id] && (
                    <div className="text-[10px] text-red-400 mt-1">{segmentError[img.evidence_id]}</div>
                  )}
                  {segmentResults[img.evidence_id] && (
                    <div className="mt-2 p-1.5 bg-zinc-950/90 rounded border border-zinc-800 text-[10px]">
                      {segmentResults[img.evidence_id].matches?.length > 0 ? (
                        <div className="flex items-center justify-between">
                          <span className="text-emerald-400 font-medium">
                            ✓ Found {segmentResults[img.evidence_id].matches.length} object(s)
                          </span>
                          <button
                            onClick={() =>
                              setSegmentResults((prev) => {
                                const next = { ...prev };
                                delete next[img.evidence_id];
                                return next;
                              })
                            }
                            className="text-[9px] text-zinc-500 hover:text-zinc-300 underline"
                          >
                            Clear Box
                          </button>
                        </div>
                      ) : (
                        <div className="text-amber-400 text-[10px]">
                          ⚠️ No objects recognized. Try single nouns (e.g. &quot;glove&quot;, &quot;crowbar&quot;, &quot;padlock&quot;).
                        </div>
                      )}
                    </div>
                  )}
                </div>
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

function EvidenceImage({
  caseId,
  evidenceId,
  alt,
  matches = [],
}: {
  caseId: string;
  evidenceId: string;
  alt: string;
  matches?: SegmentMatch[];
}) {
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
      <div className="w-full aspect-[4/3] rounded mb-2 bg-zinc-900 flex items-center justify-center text-xs text-red-400">
        Could not load image
      </div>
    );
  }

  if (!url) {
    return <div className="w-full aspect-[4/3] rounded mb-2 bg-zinc-900 animate-pulse" />;
  }

  return (
    <div className="relative w-full aspect-[4/3] rounded mb-2 overflow-hidden bg-zinc-900 select-none">
      {/* eslint-disable-next-line @next/next/no-img-element -- authenticated blob: URL, not optimisable by next/image */}
      <img src={url} alt={alt} className="w-full h-full object-cover rounded block" />

      {/* SAM 3.1 Bounding Box Overlay */}
      {matches.map((m, idx) => {
        const box = m.box;
        if (!box) return null;
        const color = m.color || "#10b981";
        return (
          <div
            key={idx}
            className="absolute border-2 transition-all duration-200 pointer-events-auto"
            style={{
              left: `${box.pct_left}%`,
              top: `${box.pct_top}%`,
              width: `${box.pct_width}%`,
              height: `${box.pct_height}%`,
              borderColor: color,
              backgroundColor: `${color}33`, // 20% opacity colored fill
              boxShadow: `0 0 12px ${color}99`,
            }}
          >
            <span
              className="absolute -top-4 left-0 px-1.5 py-0.5 rounded text-[8px] font-bold text-white shadow uppercase tracking-wider whitespace-nowrap flex items-center gap-0.5"
              style={{ backgroundColor: color }}
            >
              <span>🏷️</span>
              <span>{m.label || "OBJECT"}</span>
            </span>
          </div>
        );
      })}
    </div>
  );
}

type StudioTabProps = {
  caseId: string;
  SimulationPlayer: ComponentType<any>;
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
  caseId: string;
};

function StudioTab(props: StudioTabProps) {
  const {
    caseId,
    SimulationPlayer,
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
    caseId,
  } = props;

  const [simulation, setSimulation] = useState<any>(null);
  const [simLoading, setSimLoading] = useState(false);
  const [currentFrameIdx, setCurrentFrameIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [cameraPreset, setCameraPreset] = useState("overview");
  const [viewMode, setViewMode] = useState<"simulation" | "procedural">("simulation");

  useEffect(() => {
    if (!caseId) return;
    setSimLoading(true);
    api
      .getSimulation(caseId)
      .then((data) => {
        setSimulation(data);
        if (data?.frames?.length > 0) setCurrentFrameIdx(0);
      })
      .catch((e) => console.error("Could not load simulation:", e))
      .finally(() => setSimLoading(false));
  }, [caseId]);

  const handleRegenerateSim = async () => {
    setSimLoading(true);
    try {
      const data = await api.generateSimulation(caseId);
      setSimulation(data);
      setCurrentFrameIdx(0);
    } catch (e) {
      console.error("Could not regenerate simulation:", e);
    } finally {
      setSimLoading(false);
    }
  };

  const selectedPanelRef = useRef<HTMLDivElement | null>(null);
  const chatEnd = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    chatEnd.current?.scrollIntoView({ block: "end" });
  }, [chatHistory]);
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

<<<<<<< HEAD
        <div className="border border-zinc-800 rounded-xl p-4 bg-zinc-950/60 shadow-xl">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 pb-3 mb-4">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setViewMode("simulation")}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
                  viewMode === "simulation"
                    ? "bg-indigo-600 text-white shadow-lg shadow-indigo-900/40"
                    : "bg-zinc-900 text-zinc-400 hover:text-white"
                }`}
              >
                <span>🎬</span>
                <span>4D Forensic Simulation</span>
                {simulation?.cached && (
                  <span className="text-[10px] bg-indigo-950 text-indigo-300 px-1.5 py-0.2 rounded border border-indigo-700/60 font-mono">
                    ⚡ 0.1s Cache
                  </span>
                )}
              </button>
              <button
                onClick={() => setViewMode("procedural")}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
                  viewMode === "procedural"
                    ? "bg-indigo-600 text-white shadow-lg shadow-indigo-900/40"
                    : "bg-zinc-900 text-zinc-400 hover:text-white"
                }`}
              >
                <span>📐</span>
                <span>Procedural Room Shell</span>
              </button>
            </div>

            {viewMode === "simulation" && (
              <div className="flex items-center gap-2">
                <button
                  onClick={handleRegenerateSim}
                  disabled={simLoading}
                  className="px-2.5 py-1 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-[11px] text-zinc-300 font-medium disabled:opacity-50 transition"
                >
                  {simLoading ? "Updating..." : "🔄 Refresh Simulation"}
                </button>
              </div>
            )}
          </div>

          {viewMode === "simulation" ? (
            simLoading && !simulation ? (
              <div className="h-96 flex flex-col items-center justify-center text-xs text-zinc-400 border border-zinc-800 rounded-lg animate-pulse gap-2">
                <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                <span>Generating 4D Chronological Incident Simulation...</span>
              </div>
            ) : simulation ? (
              <SimulationPlayer
                simulation={simulation}
                currentFrameIdx={currentFrameIdx}
                setCurrentFrameIdx={setCurrentFrameIdx}
                isPlaying={isPlaying}
                setIsPlaying={setIsPlaying}
                playbackSpeed={playbackSpeed}
                setPlaybackSpeed={setPlaybackSpeed}
                cameraPreset={cameraPreset}
                setCameraPreset={setCameraPreset}
              />
            ) : (
              <div className="h-64 flex flex-col items-center justify-center text-xs text-zinc-500 border border-dashed border-zinc-800 rounded gap-2">
                <span>No simulation data generated yet.</span>
                <button
                  onClick={handleRegenerateSim}
                  className="px-3 py-1 bg-indigo-600 text-white text-xs rounded hover:bg-indigo-500"
                >
                  Generate 4D Simulation
                </button>
              </div>
            )
          ) : (
            <div>
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
          )}
=======
                <div className="border border-zinc-800 rounded-xl p-5 bg-zinc-950/80 shadow-xl">
          <div className="mb-4">
            <h2 className="text-sm uppercase tracking-wider text-zinc-200 font-bold flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
              Scene reconstruction &amp; scenario testing
            </h2>
            <p className="text-[11px] text-zinc-400 mt-1">Hypothesis visualisation built from this case&apos;s evidence. Every element shows what it rests on; nothing here is a record of what happened.</p>
          </div>
          <ForensicSandboxPlayer caseId={caseId} />
>>>>>>> feature/investigative-sandbox
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
            <div className="space-y-3 mb-3 max-h-96 overflow-y-auto pr-2" data-testid="chat-thread">
              {chatHistory.map((turn, i) => (
                <div key={i} className="space-y-1.5">
                  <div className="flex justify-end">
                    <div className="max-w-[85%] rounded-lg rounded-br-sm bg-indigo-600/80 text-white text-xs px-3 py-2 whitespace-pre-wrap" data-testid="chat-question">{turn.question}</div>
                  </div>
                  <div className="flex justify-start">
                    <div className="max-w-[92%] rounded-lg rounded-bl-sm bg-zinc-900 border border-zinc-800 text-xs px-3 py-2" data-testid="chat-answer">
                      {turn.error ? (
                        <div className="text-red-400">{turn.error}</div>
                      ) : turn.answer === null ? (
                        <div className="text-zinc-500 italic">Thinking…</div>
                      ) : (
                        <div className="text-zinc-300 whitespace-pre-wrap">{turn.answer}</div>
                      )}
                      {turn.sources?.length > 0 && (
                        <div className="mt-2 space-y-1">
                          {turn.sources.map((s) => (
                            <div key={s.observation_id} className="border-l-2 border-zinc-700 pl-2 text-zinc-500">
                              <span className="text-zinc-600">
                                {s.extracted_time || "—"} · {s.source_evidence_id}
                              </span>
                              <div className="text-zinc-500">{s.text}</div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              <div ref={chatEnd} />
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
              // Enter that confirms a word in an input method (Tamil, Hindi, ...) must not send the message
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
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
    <div>
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
        <article className="w-full rounded-lg border border-zinc-300 bg-white shadow-lg px-8 py-7 md:px-12 md:py-9" data-testid="report-document">
          <Markdown text={reportText} />
        </article>
      ) : (
        <div className="text-sm text-zinc-600">No report loaded yet. Use Load / refresh to read it here, or Download formatted PDF for a printable copy.</div>
      )}
    </div>
  );
}

function PatternsTab({ caseId }: { caseId: string }) {
  const [loading, setLoading] = useState(true);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState("");
  const [patternsData, setPatternsData] = useState<PatternsData | null>(null);

  const loadPatterns = useCallback(async () => {
    try {
      setPatternsData(await api.getPatterns(caseId));
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load pattern intelligence");
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    let alive = true;
    api
      .getPatterns(caseId)
      .then((d) => alive && (setPatternsData(d), setError("")))
      .catch((e) => alive && setError(e instanceof ApiError ? e.message : "Failed to load pattern intelligence"))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [caseId]);

  async function handleReExtract() {
    setExtracting(true);
    setError("");
    try {
      await api.extractPatterns(caseId);
      setLoading(true);
      await loadPatterns();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to re-extract pattern fingerprint");
    } finally {
      setExtracting(false);
    }
  }

  if (loading) {
    return (
      <div className="p-8 text-center text-zinc-500">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-t-2 border-indigo-500 border-zinc-800 mb-3" />
        <div className="text-sm">Scanning case signatures and vector index...</div>
      </div>
    );
  }

  const sig = patternsData?.active_signature;
  const matches = patternsData?.similar_cases || [];
  const syn = patternsData?.comparative_synthesis;

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex items-center justify-between border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-white">Cross-Case Pattern Intelligence</h2>
            <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-indigo-900/60 text-indigo-300 border border-indigo-700/50">
              Modus Operandi Vector Engine
            </span>
            {patternsData?.cached && (
              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950/70 text-emerald-300 border border-emerald-800/60 flex items-center gap-1">
                <span>⚡</span> Cached (Instant Fetch)
              </span>
            )}
          </div>
          <p className="text-xs text-zinc-400 mt-1">
            Dense similarity matching over crime scene signatures, entry mechanics, toolmark striations, and serial syndicate tradecraft.
          </p>
        </div>
        <button
          onClick={handleReExtract}
          disabled={extracting}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-3.5 py-1.5 rounded text-xs font-medium flex items-center gap-1.5 transition-colors"
        >
          {extracting ? "Re-profiling M.O..." : "Re-analyze M.O. Fingerprint"}
        </button>
      </div>

      {error && (
        <div className="p-3 rounded border border-red-800 bg-red-950 text-red-300 text-sm">{error}</div>
      )}

      {patternsData?.status === "unavailable" && (
        <div className="p-4 rounded border border-amber-800 bg-amber-950/40 text-amber-200 text-sm" data-testid="patterns-unavailable">
          <div className="font-semibold mb-1">No modus operandi profile was produced</div>
          <div className="text-xs">{patternsData.reason} Nothing has been guessed or stored; try again when the analysis has run and the language model is reachable.</div>
        </div>
      )}
      {matches.some((m) => m.is_synthetic_reference) && (
        <div className="p-3 rounded border border-zinc-700 bg-zinc-900/60 text-zinc-300 text-xs" data-testid="patterns-synthetic-note">
          Cases marked <b>SYNTHETIC REFERENCE</b> are fictional demonstration records, not real FIRs. They show how matching works until real cases are on file.
        </div>
      )}

      {/* Active Case M.O. Card */}
      {sig && (
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
              Active Case M.O. Profile · {caseId}
            </div>
            <span className="text-xs bg-zinc-800 px-2 py-0.5 rounded text-zinc-300">
              {sig.crime_category?.replace(/_/g, " ").toUpperCase()}
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs mb-4">
            <div className="bg-zinc-950/70 p-3 rounded border border-zinc-800/60">
              <span className="text-zinc-500 block mb-1">Point of Entry</span>
              <span className="text-zinc-200 font-medium">{sig.point_of_entry}</span>
            </div>
            <div className="bg-zinc-950/70 p-3 rounded border border-zinc-800/60">
              <span className="text-zinc-500 block mb-1">Tools Identified</span>
              <span className="text-amber-300 font-medium">{sig.tools_used}</span>
            </div>
            <div className="bg-zinc-950/70 p-3 rounded border border-zinc-800/60">
              <span className="text-zinc-500 block mb-1">Target Goods</span>
              <span className="text-rose-300 font-medium">{sig.target_goods}</span>
            </div>
            <div className="bg-zinc-950/70 p-3 rounded border border-zinc-800/60">
              <span className="text-zinc-500 block mb-1">Execution Window</span>
              <span className="text-emerald-300 font-medium">{sig.timing_window}</span>
            </div>
          </div>

          <div className="mb-3">
            <div className="text-[11px] uppercase text-zinc-500 mb-1.5 font-medium">Distinctive Signatures</div>
            <div className="flex flex-wrap gap-1.5">
              {(sig.signature_traits || []).map((trait, idx) => (
                <span
                  key={idx}
                  className="bg-indigo-950/50 border border-indigo-800/60 text-indigo-200 px-2.5 py-0.5 rounded-full text-xs"
                >
                  ✓ {trait}
                </span>
              ))}
            </div>
          </div>

          <div className="text-xs text-zinc-300 bg-zinc-950/50 p-3 rounded border border-zinc-800/40 leading-relaxed">
            <span className="text-zinc-500 font-medium block mb-0.5">M.O. Executive Narrative:</span>
            {sig.mo_summary}
          </div>
        </div>
      )}

      {/* Comparative Synthesis / Serial Syndicate Warning */}
      {syn && (
        <div
          className={`border rounded-lg p-5 ${
            syn.verdict?.includes("STRONG")
              ? "bg-rose-950/30 border-rose-800/80 shadow-lg shadow-rose-950/20"
              : "bg-amber-950/20 border-amber-800/60"
          }`}
        >
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-base">🚨</span>
              <h3 className="font-semibold text-sm text-white tracking-wide">
                SERIAL CRIME INTELLIGENCE SYNTHESIS
              </h3>
            </div>
            <span
              className={`px-2.5 py-1 rounded text-xs font-bold tracking-wider ${
                syn.verdict?.includes("STRONG")
                  ? "bg-rose-600 text-white"
                  : "bg-amber-600 text-white"
              }`}
            >
              {syn.verdict}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs mt-4">
            {/* Matching Signatures */}
            <div className="bg-zinc-950/80 p-3.5 rounded border border-zinc-800">
              <div className="text-emerald-400 font-semibold mb-2 flex items-center gap-1.5">
                <span>✓</span> Identical M.O. Signatures
              </div>
              <ul className="space-y-1.5 text-zinc-300">
                {(syn.matching_traits || []).map((t: string, i: number) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <span className="text-emerald-500 mt-0.5">•</span>
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Divergent Factors */}
            <div className="bg-zinc-950/80 p-3.5 rounded border border-zinc-800">
              <div className="text-amber-400 font-semibold mb-2 flex items-center gap-1.5">
                <span>⚠</span> Divergent Factors
              </div>
              <ul className="space-y-1.5 text-zinc-300">
                {(syn.divergent_factors || []).map((d: string, i: number) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <span className="text-amber-500 mt-0.5">•</span>
                    <span>{d}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Actionable Leads */}
            <div className="bg-zinc-950/80 p-3.5 rounded border border-zinc-800">
              <div className="text-indigo-400 font-semibold mb-2 flex items-center gap-1.5">
                <span>🔍</span> Inter-Station Tactical Leads
              </div>
              <ul className="space-y-1.5 text-zinc-300">
                {(syn.inter_station_leads || []).map((l: string, i: number) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <span className="text-indigo-400 font-bold mt-0.5">→</span>
                    <span>{l}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Historical Matches Grid */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">
            Ranked Historical Crime Docket Matches ({matches.length})
          </h3>
          <span className="text-xs text-zinc-500">Vector metric: Cosine distance over M.O. space</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {matches.map((m) => {
            const isHigh = m.similarity_percentage >= 75;
            const isMed = m.similarity_percentage >= 60;
            return (
              <div
                key={m.case_id}
                className={`bg-zinc-900/40 border rounded-lg p-4 transition-all hover:border-zinc-700 ${
                  isHigh ? "border-rose-900/60" : isMed ? "border-amber-900/40" : "border-zinc-800"
                }`}
              >
                <div className="flex items-start justify-between gap-3 mb-2.5">
                  <div>
                    <h4 className="text-sm font-semibold text-white">{m.title}</h4>
                    <div className="text-xs text-zinc-400 flex items-center gap-2 mt-0.5">
                      <span>{m.jurisdiction}</span>
                      <span>•</span>
                      <span className="text-zinc-500">{m.fir_number} ({m.fir_date})</span>
                    </div>
                  </div>
                  <div
                    className={`px-2.5 py-1 rounded text-xs font-bold tabular-nums shrink-0 ${
                      isHigh
                        ? "bg-rose-900/80 text-rose-200 border border-rose-700"
                        : isMed
                        ? "bg-amber-900/80 text-amber-200 border border-amber-700"
                        : "bg-zinc-800 text-zinc-400"
                    }`}
                  >
                    {m.similarity_percentage}% MATCH
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs mb-3">
                  <div className="bg-zinc-950/60 p-2 rounded border border-zinc-800/50">
                    <span className="text-zinc-500 block text-[10px] uppercase">Entry</span>
                    <span className="text-zinc-300 font-medium">{m.point_of_entry}</span>
                  </div>
                  <div className="bg-zinc-950/60 p-2 rounded border border-zinc-800/50">
                    <span className="text-zinc-500 block text-[10px] uppercase">Tools</span>
                    <span className="text-zinc-300 font-medium">{m.tools_used}</span>
                  </div>
                  <div className="bg-zinc-950/60 p-2 rounded border border-zinc-800/50">
                    <span className="text-zinc-500 block text-[10px] uppercase">Target</span>
                    <span className="text-zinc-300 font-medium">{m.target_goods}</span>
                  </div>
                  <div className="bg-zinc-950/60 p-2 rounded border border-zinc-800/50">
                    <span className="text-zinc-500 block text-[10px] uppercase">Timing</span>
                    <span className="text-zinc-300 font-medium">{m.timing_window}</span>
                  </div>
                </div>

                <div className="text-xs text-zinc-400 bg-zinc-950/40 p-2.5 rounded border border-zinc-800/40 leading-relaxed mb-2.5">
                  {m.mo_summary}
                </div>

                <div className="flex flex-wrap gap-1">
                  {(m.signature_traits || []).slice(0, 3).map((t: string, i: number) => (
                    <span key={i} className="text-[11px] bg-zinc-800/60 text-zinc-400 px-2 py-0.5 rounded">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function LegalTab({ caseId }: { caseId: string }) {
  const [loading, setLoading] = useState(true);
  const [advisoryData, setAdvisoryData] = useState<LegalAdvisory | null>(null);
  const [error, setError] = useState("");

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedFilter, setSelectedFilter] = useState("all");
  const [searchResults, setSearchResults] = useState<LegalDoc[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [allSections, setAllSections] = useState<LegalDoc[]>([]);

  useEffect(() => {
    let alive = true;
    Promise.all([api.getLegalAdvisory(caseId), api.getLegalSections()])
      .then(([adv, sections]) => {
        if (!alive) return;
        setError("");
        setAdvisoryData(adv);
        setAllSections(sections);
        setSearchResults(sections);
      })
      .catch((e) => alive && setError(e instanceof ApiError ? e.message : "Failed to load legal intelligence"))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [caseId]);

  async function executeSearch(query: string, filterAct: string) {
    setSearchBusy(true);
    try {
      const actParam = filterAct === "all" ? undefined : filterAct;
      if (!query.trim() && filterAct === "all") {
        setSearchResults(allSections);
      } else {
        const res = await api.searchLegal(query.trim() || (filterAct !== "all" ? filterAct : "statute"), actParam);
        setSearchResults(res);
      }
    } catch (e) {
      console.error("Legal search failed:", e);
    } finally {
      setSearchBusy(false);
    }
  }

  function handleFilterClick(filterKey: string, filterLabel: string) {
    setSelectedFilter(filterKey);
    executeSearch(searchQuery, filterKey === "all" ? "all" : filterLabel);
  }

  if (loading) {
    return (
      <div className="p-8 text-center text-zinc-500">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-t-2 border-indigo-500 border-zinc-800 mb-3" />
        <div className="text-sm">Synthesizing statutory charges and auditing evidentiary compliance...</div>
      </div>
    );
  }

  const adv = advisoryData?.advisory;
  const advisoryUnavailable = advisoryData?.status === "unavailable";
  const compliance = advisoryData?.compliance_audit;
  const recommendedSections = adv?.recommended_sections || [];
  const demographic = adv?.accused_demographic_assessment;
  const complianceItems = compliance?.compliance_items || [];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="border-b border-zinc-800 pb-4">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-white">Legal references (AI draft, for review)</h2>
          <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-amber-950 text-amber-300 border border-amber-800/60">
            AI-drafted, not legal advice
          </span>
        </div>
        <p className="text-xs text-zinc-400 mt-1">
          A draft list of provisions that an AI model suggests may relate to the recorded facts, with the evidence each suggestion rests on. It is a starting point for a legal professional, not legal advice, and not a charging decision. A qualified person must confirm every section against the official text before anything is relied on.
        </p>
      </div>

      {error && (
        <div className="p-3 rounded border border-red-800 bg-red-950 text-red-300 text-sm">{error}</div>
      )}

      <div className="p-3 rounded border border-amber-800 bg-amber-950/40 text-amber-200 text-xs" data-testid="legal-verify-notice">
        {advisoryData?.notice ||
          "AI-drafted suggestions based on this case's recorded facts. This is not legal advice. Have a qualified legal professional confirm every section number, sub-clause, punishment and procedure against the official text of the Act, and the facts against the source evidence, before relying on any of it."}
      </div>
      {advisoryUnavailable && (
        <div className="p-3 rounded border border-zinc-700 bg-zinc-900/60 text-zinc-300 text-xs" data-testid="legal-unavailable">
          No sections were suggested. {advisoryData?.reason}
        </div>
      )}

      {/* SECTION 1: Statutory FIR Charge Recommendations */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300 flex items-center gap-2">
            <span>⚖️</span> Provisions an AI suggests may relate to the facts ({recommendedSections.length})
          </h3>
          <span className="text-xs text-zinc-500">Reference list only, not a charging decision</span>
        </div>

        {/* Accused Demographics Assessment Banner */}
        {demographic && (
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-3.5 flex items-center justify-between gap-4 text-xs">
            <div className="flex items-center gap-2.5">
              <span className="text-base">👤</span>
              <div>
                <span className="text-zinc-400">Age information in the record: </span>
                <span className="text-zinc-200 font-semibold">{demographic.age_assessed}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-zinc-500">Procedural Regime:</span>
              <span className="bg-zinc-800 px-2.5 py-1 rounded text-zinc-300 font-medium">
                {demographic.applicable_regime}
              </span>
            </div>
          </div>
        )}

        {/* Recommended Sections Cards */}
        <div className="grid grid-cols-1 gap-4">
          {recommendedSections.map((sec, idx) => (
            <div
              key={idx}
              className="bg-zinc-900/70 border border-zinc-800 rounded-lg p-5 transition-all hover:border-zinc-700 shadow-sm"
            >
              <div className="flex items-start justify-between gap-4 mb-3">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="bg-indigo-950/80 text-indigo-300 border border-indigo-800 px-2.5 py-0.5 rounded text-xs font-bold tracking-wide">
                      {sec.act} — Section {sec.section}
                    </span>
                    {sec.cognizable && (
                      <span className="bg-rose-950/70 text-rose-300 border border-rose-800/60 px-2 py-0.5 rounded text-[10px] font-bold">
                        COGNIZABLE
                      </span>
                    )}
                    {sec.bailable === false ? (
                      <span className="bg-purple-950/70 text-purple-300 border border-purple-800/60 px-2 py-0.5 rounded text-[10px] font-bold">
                        NON-BAILABLE
                      </span>
                    ) : sec.bailable === true ? (
                      <span className="bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded text-[10px]">
                        BAILABLE
                      </span>
                    ) : (
                      <span className="bg-zinc-900 text-zinc-500 border border-zinc-800 px-2 py-0.5 rounded text-[10px]" title="Neither the model nor the legal corpus states whether this offence is bailable. Check the official text.">
                        BAILABILITY NOT STATED
                      </span>
                    )}
                    {sec.punishment ? (
                      <span className="bg-amber-950/50 text-amber-300 border border-amber-800/40 px-2 py-0.5 rounded text-[10px]">
                        {sec.punishment}
                      </span>
                    ) : (
                      <span className="bg-zinc-900 text-zinc-500 border border-zinc-800 px-2 py-0.5 rounded text-[10px]">punishment not stated</span>
                    )}
                  </div>
                  <h4 className="text-sm font-semibold text-white mt-1.5">{sec.title}</h4>
                </div>
                <div className="text-right text-xs text-zinc-400 shrink-0">
                  <span className="text-zinc-500 block text-[10px] uppercase">Triable By</span>
                  <span className="font-medium text-zinc-300">{sec.triable_by || "not stated"}</span>
                  {sec.details_source && <span className="block text-[9px] text-zinc-600 max-w-[200px]" title={sec.details_source}>punishment, bail and court from the bundled legal summary</span>}
                </div>
              </div>

              {/* Justification based on case facts */}
              <div className="text-xs text-zinc-300 bg-zinc-950/60 p-3 rounded border border-zinc-800/60 leading-relaxed mb-3">
                <span className="text-indigo-400 font-semibold block mb-0.5">Evidentiary Justification:</span>
                {sec.justification}
              </div>

              {/* Statutory Ingredients Checklist */}
              <div>
                <span className="text-[11px] uppercase text-zinc-500 font-semibold block mb-1.5">
                  Statutory Ingredients Satisfied:
                </span>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                  {(sec.statutory_ingredients_met || []).map((ing: string, i: number) => (
                    <div key={i} className="flex items-start gap-1.5 bg-zinc-950/40 p-2 rounded border border-zinc-900">
                      <span className="text-emerald-400 font-bold shrink-0">✓</span>
                      <span className="text-zinc-300">{ing}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* SECTION 2: Evidentiary Admissibility & Procedural Safeguards Audit */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300 flex items-center gap-2">
            <span>🛡️</span> Procedural & Evidentiary Admissibility Audit ({complianceItems.length})
          </h3>
          <span className="text-xs text-zinc-500">Judicial compliance with Supreme Court mandates</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {complianceItems.map((item, idx) => {
            const isCrit = item.severity === "CRITICAL" || item.severity === "HIGH";
            return (
              <div
                key={idx}
                className={`bg-zinc-900/60 border rounded-lg p-4 ${
                  isCrit ? "border-amber-900/60 bg-amber-950/10" : "border-zinc-800"
                }`}
              >
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div>
                    <h4 className="text-xs font-semibold text-white">{item.rule}</h4>
                    <span className="text-[11px] text-zinc-400 block">{item.statute}</span>
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold shrink-0 ${
                      item.status === "SATISFIED" || item.status === "COMPLIANT" || item.status === "ADULT_REGIME_CONFIRMED"
                        ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                        : "bg-amber-950 text-amber-300 border border-amber-800"
                    }`}
                  >
                    {item.status}
                  </span>
                </div>
                <p className="text-xs text-zinc-300 leading-relaxed mb-2.5">{item.details}</p>
                <div className="text-[11px] text-zinc-500 bg-zinc-950/50 px-2.5 py-1.5 rounded border border-zinc-900 flex items-center justify-between">
                  <span>Mandatory Statutory Form:</span>
                  <code className="text-zinc-300 font-mono text-[10px]">{item.statutory_form}</code>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* SECTION 3: Universal Legal Intelligence Search & Corpus Explorer */}
      <div className="space-y-4 pt-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300 flex items-center gap-2">
            <span>🔍</span> Universal Legal Corpus Search & Precedents
          </h3>
          <span className="text-xs text-zinc-500">20+ Indexed Statutes & Supreme Court Rulings</span>
        </div>

        {/* Search Input Bar */}
        <div className="bg-zinc-900/80 border border-zinc-800 rounded-lg p-4 space-y-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              executeSearch(searchQuery, selectedFilter === "all" ? "all" : selectedFilter);
            }}
            className="flex gap-2"
          >
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search section number (e.g. BNS 331, NDPS 21), legal doctrine, or natural query..."
              className="flex-1 bg-zinc-950 border border-zinc-800 rounded px-3.5 py-2 text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500"
            />
            <button
              type="submit"
              disabled={searchBusy}
              className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-4 py-2 rounded text-xs font-semibold transition-colors"
            >
              {searchBusy ? "Searching..." : "Search Corpus"}
            </button>
          </form>

          {/* Filter Chips */}
          <div className="flex flex-wrap gap-1.5 text-xs">
            {[
              { id: "all", label: "All Statutes" },
              { id: "bns", label: "BNS 2023" },
              { id: "bnss", label: "BNSS 2023" },
              { id: "bsa", label: "BSA 2023" },
              { id: "ndps", label: "NDPS Act" },
              { id: "juvenile", label: "JJ Act / POCSO" },
              { id: "precedent", label: "Landmark Precedents" },
            ].map((chip) => (
              <button
                key={chip.id}
                type="button"
                onClick={() => handleFilterClick(chip.id, chip.label)}
                className={`px-3 py-1 rounded text-[11px] font-medium transition-colors ${
                  selectedFilter === chip.id
                    ? "bg-indigo-700 text-white"
                    : "bg-zinc-950 text-zinc-400 hover:text-zinc-200 border border-zinc-800"
                }`}
              >
                {chip.label}
              </button>
            ))}
          </div>
        </div>

        {/* Results Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {searchResults.map((doc) => (
            <div
              key={doc.id}
              className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-4 space-y-2 hover:border-zinc-750 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider block">
                    {doc.act || "Statutory Code"}
                  </span>
                  <h4 className="text-sm font-semibold text-white">{doc.title}</h4>
                </div>
                {doc.cognizable !== undefined && doc.cognizable !== null && (
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold shrink-0 ${
                      doc.cognizable ? "bg-rose-950/80 text-rose-300" : "bg-zinc-800 text-zinc-400"
                    }`}
                  >
                    {doc.cognizable ? "COGNIZABLE" : "NON-COGNIZABLE"}
                  </span>
                )}
              </div>

              {doc.punishment && (
                <div className="text-[11px] text-amber-300/90 font-medium">
                  ⚖️ {doc.punishment}
                </div>
              )}

              <p className="text-xs text-zinc-300 leading-relaxed bg-zinc-950/50 p-2.5 rounded border border-zinc-900">
                {doc.text}
              </p>
              {doc.verification_status && doc.verification_status !== "verified" && (
                <div className="text-[10px] text-amber-400/90" title="This entry is a summary written for this tool, not the official text">
                  Summary, not the official text — verify against the Act or judgment before citing.
                </div>
              )}

              {doc.ingredients && doc.ingredients.length > 0 && (
                <div className="pt-1">
                  <span className="text-[10px] uppercase text-zinc-500 font-semibold block mb-1">
                    Key Legal Ingredients:
                  </span>
                  <ul className="space-y-1 text-[11px] text-zinc-400">
                    {doc.ingredients.slice(0, 3).map((ing: string, i: number) => (
                      <li key={i} className="flex items-start gap-1">
                        <span className="text-indigo-400">•</span>
                        <span>{ing}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
