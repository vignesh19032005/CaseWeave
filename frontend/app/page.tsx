"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, clearToken, ApiError } from "./lib/api";

type Case = { case_id: string; title: string; created_at: string };

export default function CommandCenter() {
  const router = useRouter();
  const [cases, setCases] = useState<Case[] | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  function refresh() {
    api
      .listCases()
      .then(setCases)
      .catch((e) => {
        setCases([]);
        setError(e instanceof ApiError ? e.message : "Could not reach CaseWeave API on :8010 — is the backend running?");
      });
  }

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    // An expired/invalid token is handled inside api.request (401 -> login);
    // other failures (backend down) should show an error, not log the user out.
    api
      .me()
      .then((u) => {
        setUsername(u.username);
        setRole(u.role);
      })
      .catch(() => {});
    refresh();
  }, [router]);

  async function createCase() {
    setError("");
    try {
      const c = await api.createCase(title || "Untitled Case");
      setTitle("");
      router.push(`/case/${c.case_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create case");
    }
  }

  async function deleteCase(c: Case, ev: React.MouseEvent) {
    ev.stopPropagation();
    if (!confirm(`Permanently delete "${c.title}" (${c.case_id}) and all its evidence? This cannot be undone.`)) return;
    setDeletingId(c.case_id);
    setError("");
    try {
      await api.deleteCase(c.case_id);
      setCases((prev) => prev?.filter((x) => x.case_id !== c.case_id) ?? null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete case");
    } finally {
      setDeletingId(null);
    }
  }

  function logout() {
    clearToken();
    router.push("/login");
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-xl font-semibold">CaseWeave AI</h1>
          {username && (
            <div className="flex items-center gap-3 text-xs text-zinc-500">
              <span>{username}</span>
              {role === "admin" && (
                <button onClick={() => router.push("/users")} className="hover:text-zinc-300 underline">
                  users
                </button>
              )}
              <button onClick={logout} className="hover:text-zinc-300 underline">
                sign out
              </button>
            </div>
          )}
        </div>
        <p className="text-sm text-zinc-500 mb-6">Case Command Center — evidence-linked investigation workspace</p>

        {error && (
          <div className="mb-4 p-3 rounded border border-red-800 bg-red-950 text-red-300 text-sm">{error}</div>
        )}

        <div className="border border-zinc-800 rounded-lg p-4 mb-6 flex gap-3">
          <input
            className="flex-1 bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm"
            placeholder="New case title (e.g. Warehouse Incident)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && createCase()}
          />
          <button className="bg-indigo-600 hover:bg-indigo-500 rounded px-4 py-2 text-sm font-medium" onClick={createCase}>
            New case
          </button>
        </div>

        <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-900">
          {cases === null && <div className="p-4 text-sm text-zinc-500">Loading cases...</div>}
          {cases?.length === 0 && <div className="p-4 text-sm text-zinc-600">No cases yet — create one above.</div>}
          {cases?.map((c) => (
            <div
              key={c.case_id}
              onClick={() => router.push(`/case/${c.case_id}`)}
              className="w-full text-left p-4 hover:bg-zinc-900 flex items-center justify-between cursor-pointer"
            >
              <div>
                <div className="text-sm font-medium">{c.title}</div>
                <div className="text-xs text-zinc-500">{c.case_id}</div>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-xs text-zinc-600">{new Date(c.created_at).toLocaleString()}</div>
                {role === "admin" && (
                  <button
                    onClick={(e) => deleteCase(c, e)}
                    disabled={deletingId === c.case_id}
                    className="text-xs text-red-500 hover:text-red-400 disabled:opacity-50 px-2 py-1"
                    title="Delete case"
                  >
                    {deletingId === c.case_id ? "deleting…" : "delete"}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
