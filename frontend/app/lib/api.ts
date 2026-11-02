// Shared API client: base URL + auth token handling for every CaseWeave
// endpoint. All endpoints require a Bearer JWT (Stage 12 RBAC) — this
// centralizes that instead of repeating it in every fetch call.

export const API = "http://127.0.0.1:8010";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("cw_token");
}

export function setToken(token: string) {
  window.localStorage.setItem("cw_token", token);
}

export function clearToken() {
  window.localStorage.removeItem("cw_token");
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function handleUnauthorized() {
  clearToken();
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

async function request(path: string, init: RequestInit = {}) {
  const token = getToken();
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, { ...init, headers });
  // A 401 from /auth/login means bad credentials, not an expired session —
  // let it fall through so the login form shows the server's message.
  if (res.status === 401 && path !== "/auth/login") {
    handleUnauthorized();
    throw new ApiError(401, "session expired — redirecting to login");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // not JSON — keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return res.json();
  return res.text();
}

export const api = {
  login: (username: string, password: string) =>
    request("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  me: () => request("/auth/me"),

  listCases: () => request("/cases"),
  getCase: (caseId: string) => request(`/cases/${caseId}`),
  createCase: (title: string) =>
    request("/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),

  listEvidence: (caseId: string) => request(`/cases/${caseId}/evidence`),
  // Evidence files require the bearer token, so <img src> can't load them
  // directly — fetch as a blob and hand back an object URL instead.
  evidenceFileUrl: async (caseId: string, evidenceId: string) => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API}/cases/${caseId}/evidence/${evidenceId}/file`, { headers });
    if (res.status === 401) {
      handleUnauthorized();
      throw new ApiError(401, "session expired — redirecting to login");
    }
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    return URL.createObjectURL(await res.blob());
  },
  uploadEvidence: async (caseId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API}/cases/${caseId}/evidence`, { method: "POST", body: form, headers });
    if (res.status === 401) {
      handleUnauthorized();
      throw new ApiError(401, "session expired — redirecting to login");
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, body.detail || res.statusText);
    }
    return res.json();
  },

  processCase: (caseId: string, legalQuery?: string) =>
    request(`/cases/${caseId}/process`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ legal_query: legalQuery || null }),
    }),
  processStatus: (caseId: string, jobId: string) => request(`/cases/${caseId}/process/status/${jobId}`),

  getTimeline: (caseId: string) => request(`/cases/${caseId}/timeline`),
  getAudit: (caseId: string) => request(`/cases/${caseId}/audit`),
  getConflicts: (caseId: string) => request(`/cases/${caseId}/conflicts`),
  getEvidenceLinks: (caseId: string) => request(`/cases/${caseId}/evidence-links`),
  reviewConflict: (caseId: string, conflictId: string, status: string, reason: string) =>
    request(`/cases/${caseId}/conflicts/${conflictId}/review`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, reason }),
    }),
  getConflictReviews: (caseId: string, conflictId: string) =>
    request(`/cases/${caseId}/conflicts/${conflictId}/reviews`),

  downloadEvidenceCertificate: async (caseId: string, evidenceId: string) => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API}/cases/${caseId}/evidence/${evidenceId}/certificate`, { headers });
    if (res.status === 401) {
      handleUnauthorized();
      throw new ApiError(401, "session expired — redirecting to login");
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, body.detail || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Draft_Certificate_${evidenceId}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  getEntities: (caseId: string) => request(`/cases/${caseId}/entities`),
  resolveEntities: (caseId: string) => request(`/cases/${caseId}/entities/resolve`, { method: "POST" }),

  reconstruct: (caseId: string) => request(`/cases/${caseId}/reconstruct`, { method: "POST" }),

  askCase: (caseId: string, question: string, history: { question: string; answer: string }[] = []) =>
    request(`/cases/${caseId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
    }),

  deleteCase: (caseId: string) => request(`/cases/${caseId}`, { method: "DELETE" }),

  segmentEvidence: (caseId: string, evidenceId: string, prompt: string) =>
    request(`/cases/${caseId}/evidence/${evidenceId}/segment`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    }),

  getReport: (caseId: string) => request(`/cases/${caseId}/report`),
  downloadReportPdf: async (caseId: string) => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API}/cases/${caseId}/report/pdf`, { headers });
    if (res.status === 401) {
      handleUnauthorized();
      throw new ApiError(401, "session expired — redirecting to login");
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, body.detail || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `CaseWeave_Report_${caseId}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  getPatterns: (caseId: string) => request(`/cases/${caseId}/patterns`),
  extractPatterns: (caseId: string) => request(`/cases/${caseId}/patterns/extract`, { method: "POST" }),

  searchLegal: (query: string, act?: string) =>
    request(`/legal/search?q=${encodeURIComponent(query)}${act ? `&act=${encodeURIComponent(act)}` : ""}`),
  getLegalSections: () => request("/legal/sections"),
  getLegalCompliance: (caseId: string) => request(`/cases/${caseId}/legal-compliance`),
  getLegalAdvisory: (caseId: string) => request(`/cases/${caseId}/legal-advisory`),

  // Scene reconstruction sandbox. GET never generates; generation is an explicit POST
  // that runs in the background and is polled via getSandbox.
  getSandbox: (caseId: string) => request(`/cases/${caseId}/sandbox`),
  getSandboxRun: (caseId: string, runId: string) => request(`/cases/${caseId}/sandbox/runs/${runId}`),
  generateSandbox: (caseId: string, mode: "full" | "scenarios_only") =>
    request(`/cases/${caseId}/sandbox/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    }),
  approveSandboxLayout: (caseId: string) => request(`/cases/${caseId}/sandbox/approve-layout`, { method: "POST" }),
  sandboxInterview: (caseId: string, hypothesisText: string) =>
    request(`/cases/${caseId}/sandbox/interview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hypothesis_text: hypothesisText }),
    }),
  createOfficerScenario: (caseId: string, hypothesisText: string, interview: { question: string; answer: string }[]) =>
    request(`/cases/${caseId}/sandbox/scenarios`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hypothesis_text: hypothesisText, interview }),
    }),
  retractScenario: (caseId: string, scenarioId: string, reason: string) =>
    request(`/cases/${caseId}/sandbox/scenarios/${scenarioId}/retract`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    }),
  editSandboxLayout: (caseId: string, ops: { op: string; kind: string; id?: string; fields?: Record<string, unknown> }[]) =>
    request(`/cases/${caseId}/sandbox/layout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ops }),
    }),
  createPhotoLinks: (caseId: string) => request(`/cases/${caseId}/sandbox/photo-links`, { method: "POST" }),
  getPhotoLinks: (caseId: string) => request(`/cases/${caseId}/sandbox/photo-links`),
  getNarrative: (caseId: string) => request(`/cases/${caseId}/narrative`),
  downloadSandboxPdf: async (caseId: string) => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API}/cases/${caseId}/sandbox/export.pdf`, { headers });
    if (res.status === 401) {
      handleUnauthorized();
      throw new ApiError(401, "session expired — redirecting to login");
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, body.detail || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `CaseWeave_Scene_Review_${caseId}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  downloadSandboxPack: async (caseId: string) => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API}/cases/${caseId}/sandbox/export`, { headers });
    if (res.status === 401) {
      handleUnauthorized();
      throw new ApiError(401, "session expired — redirecting to login");
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, body.detail || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `CaseWeave_Scene_Review_Pack_${caseId}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};
