"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, ApiError } from "../lib/api";

type UserRow = { user_id: string; username: string; role: string; created_at: string; must_change_password: number | boolean };

const ROLES = ["investigator", "reviewer", "admin"];

export default function UsersPage() {
  const router = useRouter();
  const [me, setMe] = useState<{ user_id: string; role: string } | null>(null);
  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("investigator");

  const reload = useCallback(async () => {
    try {
      setUsers(await api.listUsers());
    } catch (e) {
      setUsers([]);
      setError(e instanceof ApiError ? e.message : "Could not load users");
    }
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api
      .me()
      .then((u) => {
        setMe(u);
        if (u.role !== "admin") router.push("/");
      })
      .catch(() => undefined);
    let alive = true;
    api
      .listUsers()
      .then((rows) => alive && setUsers(rows))
      .catch((e) => {
        if (!alive) return;
        setUsers([]);
        setError(e instanceof ApiError ? e.message : "Could not load users");
      });
    return () => {
      alive = false;
    };
  }, [router]);

  async function act(fn: () => Promise<unknown>, done: string) {
    setError("");
    setNotice("");
    try {
      await fn();
      setNotice(done);
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That did not work");
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    await act(() => api.createUser(username.trim(), password, role), `Created ${username.trim()}.`);
    setUsername("");
    setPassword("");
  }

  function reset(u: UserRow) {
    const pw = window.prompt(`New temporary password for ${u.username} (at least 10 characters). They must change it at next sign-in.`);
    if (!pw) return;
    void act(() => api.resetUserPassword(u.user_id, pw), `Password reset for ${u.username}; they must choose a new one at next sign-in.`);
  }

  function remove(u: UserRow) {
    if (!window.confirm(`Delete the account ${u.username}? Their past actions stay in the audit trail.`)) return;
    void act(() => api.deleteUser(u.user_id), `Deleted ${u.username}.`);
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6">
      <div className="w-full">
        <button onClick={() => router.push("/")} className="text-xs text-zinc-500 hover:text-zinc-300 mb-2">
          ← Case Command Center
        </button>
        <h1 className="text-xl font-semibold mb-1">Users</h1>
        <p className="text-sm text-zinc-500 mb-6">Investigators build cases, reviewers confirm conflicts and approve layouts, admins manage users and delete cases.</p>

        {error && <div className="mb-4 p-3 rounded border border-red-800 bg-red-950 text-red-300 text-sm">{error}</div>}
        {notice && <div className="mb-4 p-3 rounded border border-emerald-800 bg-emerald-950/50 text-emerald-300 text-sm">{notice}</div>}

        <form onSubmit={create} className="border border-zinc-800 rounded-lg p-4 mb-6 grid grid-cols-1 md:grid-cols-4 gap-3">
          <input
            className="bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm"
            placeholder="username"
            autoComplete="off"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <input
            type="password"
            className="bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm"
            placeholder="temporary password (10+ chars)"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <select className="bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm" value={role} onChange={(e) => setRole(e.target.value)}>
            {ROLES.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
          <button className="bg-indigo-600 hover:bg-indigo-500 rounded px-4 py-2 text-sm font-medium" type="submit">
            Add user
          </button>
        </form>

        <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-900">
          {users === null && <div className="p-4 text-sm text-zinc-500">Loading…</div>}
          {users?.map((u) => (
            <div key={u.user_id} className="p-3 flex items-center justify-between gap-3 text-sm" data-testid="user-row">
              <div>
                <div className="font-medium">
                  {u.username}
                  {me?.user_id === u.user_id && <span className="ml-2 text-[10px] text-zinc-500">(you)</span>}
                </div>
                <div className="text-xs text-zinc-500">
                  {u.role}
                  {Boolean(u.must_change_password) && " · must choose a new password"}
                </div>
              </div>
              <div className="flex gap-3 text-xs">
                <button onClick={() => reset(u)} className="text-zinc-400 hover:text-zinc-200 underline">
                  reset password
                </button>
                {me?.user_id !== u.user_id && (
                  <button onClick={() => remove(u)} className="text-red-500 hover:text-red-400 underline">
                    delete
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
