"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, setToken, ApiError } from "../lib/api";

const MIN_LENGTH = 10;

export default function ChangePasswordPage() {
  const router = useRouter();
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) router.push("/login");
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (newPassword.length < MIN_LENGTH) return setError(`The new password must be at least ${MIN_LENGTH} characters.`);
    if (new TextEncoder().encode(newPassword).length > 72) return setError("The new password must be at most 72 bytes.");
    if (newPassword !== confirm) return setError("The two new passwords do not match.");
    setBusy(true);
    try {
      const data = await api.changePassword(oldPassword, newPassword);
      setToken(data.access_token);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change the password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-sm border border-zinc-800 rounded-lg p-6">
        <h1 className="text-lg font-semibold mb-1">Choose a new password</h1>
        <p className="text-xs text-zinc-500 mb-6">This account must set its own password before it can be used.</p>

        {error && <div className="mb-4 p-3 rounded border border-red-800 bg-red-950 text-red-300 text-xs">{error}</div>}

        <label className="block text-xs text-zinc-500 mb-1">Current password</label>
        <input
          type="password"
          autoComplete="current-password"
          className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm mb-3"
          value={oldPassword}
          onChange={(e) => setOldPassword(e.target.value)}
        />
        <label className="block text-xs text-zinc-500 mb-1">New password (at least {MIN_LENGTH} characters)</label>
        <input
          type="password"
          autoComplete="new-password"
          className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm mb-3"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
        <label className="block text-xs text-zinc-500 mb-1">Repeat the new password</label>
        <input
          type="password"
          autoComplete="new-password"
          className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm mb-4"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        <button
          type="submit"
          disabled={busy}
          className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded px-4 py-2 text-sm font-medium"
        >
          {busy ? "Saving..." : "Change password"}
        </button>
      </form>
    </div>
  );
}
