"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken, ApiError } from "../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("TEAM AKASHI");
  const [password, setPassword] = useState("CASEWEAVE");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleLogin(user = username, pass = password) {
    setError("");
    setBusy(true);
    try {
      const data = await api.login(user, pass);
      setToken(data.access_token);
      router.push(data.must_change_password ? "/change-password" : "/");
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Could not reach CaseWeave API. Is the backend running on port 8010?");
    } finally {
      setBusy(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await handleLogin();
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-sm border border-zinc-800 rounded-xl p-6 bg-zinc-900/40 shadow-2xl backdrop-blur">
        <h1 className="text-xl font-bold mb-1 tracking-tight">CaseWeave AI</h1>
        <p className="text-xs text-zinc-500 mb-5">Forensic Digital Twin & Investigation Workspace</p>

        {/* Demo Credentials Helper Banner */}
        <div className="mb-5 p-3 rounded-lg bg-emerald-950/40 border border-emerald-800/80 text-xs">
          <div className="flex items-center justify-between text-emerald-400 font-semibold mb-1.5">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              Demo Credentials Loaded
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/60 border border-emerald-700 font-mono">Admin</span>
          </div>
          <p className="text-[11px] text-zinc-300 font-mono">
            Username: <strong className="text-emerald-300">TEAM AKASHI</strong><br />
            Password: <strong className="text-emerald-300">CASEWEAVE</strong>
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded border border-red-800 bg-red-950 text-red-300 text-xs">{error}</div>
        )}

        <label className="block text-xs text-zinc-400 mb-1">Username</label>
        <input
          className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm mb-3 focus:outline-none focus:border-indigo-500 text-zinc-100 font-medium"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          autoFocus
        />
        <label className="block text-xs text-zinc-400 mb-1">Password</label>
        <input
          type="password"
          autoComplete="current-password"
          className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm mb-5 focus:outline-none focus:border-indigo-500 text-zinc-100 font-medium"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button
          type="submit"
          disabled={busy}
          className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg px-4 py-2.5 text-sm font-semibold transition active:scale-[0.99] shadow-lg shadow-indigo-900/30 flex items-center justify-center gap-2"
        >
          {busy ? (
            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
          ) : (
            <span>Sign in as TEAM AKASHI &rarr;</span>
          )}
        </button>
      </form>
    </div>
  );
}
