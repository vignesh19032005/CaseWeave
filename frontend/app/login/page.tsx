"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken, ApiError } from "../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const data = await api.login(username, password);
      setToken(data.access_token);
      router.push(data.must_change_password ? "/change-password" : "/");
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Could not reach CaseWeave API. Is the backend running on port 8010?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-sm border border-zinc-800 rounded-lg p-6">
        <h1 className="text-lg font-semibold mb-1">CaseWeave AI</h1>
        <p className="text-xs text-zinc-500 mb-6">Investigation workspace — sign in to continue</p>

        {error && (
          <div className="mb-4 p-3 rounded border border-red-800 bg-red-950 text-red-300 text-xs">{error}</div>
        )}

        <label className="block text-xs text-zinc-500 mb-1">Username</label>
        <input
          className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm mb-3"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          autoFocus
        />
        <label className="block text-xs text-zinc-500 mb-1">Password</label>
        <input
          type="password"
          autoComplete="current-password"
          className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm mb-4"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button
          type="submit"
          disabled={busy}
          className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded px-4 py-2 text-sm font-medium"
        >
          {busy ? "Signing in..." : "Sign in"}
        </button>
        <p className="text-[11px] text-zinc-600 mt-4">
          The administrator account is created on the first run of the API; its password is set by CASEWEAVE_ADMIN_PASSWORD, or, if that is not
          set, you will be asked to choose a new one at first sign-in.
        </p>
      </form>
    </div>
  );
}
