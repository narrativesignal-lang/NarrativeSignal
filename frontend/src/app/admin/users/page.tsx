"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Shell } from "@/components/Shell";
import { api, parseApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useUser } from "@/lib/UserContext";

type UserRow = {
  id: string;
  username: string;
  email: string;
  is_admin: boolean;
  paid_access: boolean;
  credits_balance: number;
  created_at: string | null;
  token_version: number;
};

function obviousTestUser(u: UserRow): boolean {
  const em = (u.email || "").toLowerCase();
  const un = (u.username || "").toLowerCase();
  if (em.endsWith("@example.com")) return true;
  for (const p of ["burst_", "e2e_", "auth_e2e_", "loadtest_", "test_user_", "playwright_"]) {
    if (un.startsWith(p)) return true;
  }
  if (un.includes("e2e") || em.includes("e2e")) return true;
  return false;
}

export default function AdminUsersPage() {
  const { user, loading: userLoading } = useUser();
  const { t } = useI18n();
  const [users, setUsers] = useState<UserRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [patchingId, setPatchingId] = useState<string | null>(null);
  const [showLoadTest, setShowLoadTest] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmBulkOpen, setConfirmBulkOpen] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [testDeleteBusy, setTestDeleteBusy] = useState(false);
  const [syncBusy, setSyncBusy] = useState(false);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);

  const refreshUsers = useCallback(async () => {
    const list = await api.listUsers({ include_load_test: showLoadTest });
    setUsers(list);
    setSelected(new Set());
  }, [showLoadTest]);

  useEffect(() => {
    if (userLoading) return;
    if (!user?.is_admin) {
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .listUsers({ include_load_test: showLoadTest })
      .then(setUsers)
      .catch((e: unknown) => setError(parseApiError(e)))
      .finally(() => setLoading(false));
  }, [user?.is_admin, userLoading, user?.id, showLoadTest]);

  const selectableIds = useMemo(
    () => users.filter((u) => u.id !== user?.id).map((u) => u.id),
    [users, user?.id]
  );
  const selectedCount = useMemo(
    () => [...selected].filter((id) => selectableIds.includes(id)).length,
    [selected, selectableIds]
  );
  const allSelectableSelected =
    selectableIds.length > 0 && selectableIds.every((id) => selected.has(id));

  const toggleRow = (id: string) => {
    if (id === user?.id) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (allSelectableSelected) {
      setSelected(new Set());
      return;
    }
    setSelected(new Set(selectableIds));
  };

  if (userLoading) {
    return (
      <Shell>
        <div className="mx-auto max-w-2xl p-6">
          <p className="text-sm text-slate-400">{t("common.loading")}</p>
        </div>
      </Shell>
    );
  }

  if (!user?.is_admin) {
    return (
      <Shell>
        <div className="mx-auto max-w-2xl p-6">
          <p className="text-amber-200">{t("admin.accessRequired")}</p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="mx-auto max-w-5xl p-6">
        <h1 className="text-xl font-semibold text-slate-100">{t("nav.admin")} — Users</h1>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-slate-400">All registered users ({users.length})</p>
          <label className="flex items-center gap-2 text-xs text-slate-300">
            <input
              type="checkbox"
              checked={showLoadTest}
              onChange={(e) => setShowLoadTest(e.target.checked)}
              className="h-4 w-4 accent-slate-500"
            />
            Show load-test users (burst_*@example.com)
          </label>
        </div>

        {selectedCount > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-slate-600 bg-slate-800/40 px-4 py-2 text-sm text-slate-200">
            <span>
              {selectedCount} selected
            </span>
            <button
              type="button"
              disabled={bulkBusy}
              onClick={() => setConfirmBulkOpen(true)}
              className="rounded border border-red-800/80 bg-red-950/40 px-3 py-1 text-xs font-medium text-red-200 hover:bg-red-950/60 disabled:opacity-50"
            >
              Delete selected
            </button>
          </div>
        )}

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={testDeleteBusy}
            onClick={async () => {
              if (!confirm("Delete all obvious test users (example.com, e2e_*, burst_*, etc.)? This cannot be undone.")) return;
              setTestDeleteBusy(true);
              setError(null);
              try {
                const r = await api.deleteObviousTestAdminUsers();
                await refreshUsers();
                if (r.deleted === 0) setError("No matching test users to delete.");
                else setError(null);
              } catch (e: unknown) {
                setError(parseApiError(e));
              } finally {
                setTestDeleteBusy(false);
              }
            }}
            className="rounded border border-slate-600 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
          >
            Delete obvious test users
          </button>
          <button
            type="button"
            disabled={syncBusy}
            onClick={async () => {
              setError(null);
              setSyncNotice(null);
              setSyncBusy(true);
              try {
                const r = await api.adminSyncSearchTrends();
                setError(null);
                setSyncNotice(`Synced ${r.entities} entities, ${r.metric_rows} metric rows.`);
              } catch (e: unknown) {
                setError(parseApiError(e));
              } finally {
                setSyncBusy(false);
              }
            }}
            className="rounded border border-slate-600 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
          >
            {syncBusy ? "Syncing…" : "Sync search trends now (all entities)"}
          </button>
        </div>

        {syncNotice ? (
          <p className="mt-3 text-xs text-emerald-400/90" role="status">
            {syncNotice}
          </p>
        ) : null}

        {loading ? (
          <p className="mt-6 text-sm text-slate-500">Loading data...</p>
        ) : error ? (
          <div className="mt-6 rounded border border-red-900/50 bg-red-950/20 px-4 py-2 text-sm text-red-200">
            {error}
          </div>
        ) : (
          <div className="mt-6 overflow-x-auto rounded-lg border border-slate-700 bg-slate-900/50">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700 bg-slate-800/60">
                  <th className="w-10 px-2 py-3">
                    <input
                      type="checkbox"
                      aria-label="Select all users"
                      checked={allSelectableSelected}
                      onChange={toggleSelectAll}
                      disabled={selectableIds.length === 0}
                      className="h-4 w-4 accent-slate-500"
                    />
                  </th>
                  <th className="px-4 py-3 font-medium text-slate-200">Username</th>
                  <th className="px-4 py-3 font-medium text-slate-200">Email</th>
                  <th className="px-4 py-3 font-medium text-slate-200">Role</th>
                  <th className="px-4 py-3 font-medium text-slate-200">Paid timeline</th>
                  <th className="px-4 py-3 font-medium text-slate-200">Credits</th>
                  <th className="px-4 py-3 font-medium text-slate-200">Created</th>
                  <th className="px-4 py-3 font-medium text-slate-200">Session</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr
                    key={u.id}
                    className={`border-b border-slate-800/60 ${
                      u.is_admin ? "bg-amber-950/20" : ""
                    }`}
                  >
                    <td className="px-2 py-3">
                      {u.id === user.id ? (
                        <span className="text-[10px] text-slate-600" title="Cannot delete your own account">
                          —
                        </span>
                      ) : (
                        <input
                          type="checkbox"
                          checked={selected.has(u.id)}
                          onChange={() => toggleRow(u.id)}
                          className="h-4 w-4 accent-slate-500"
                          aria-label={`Select ${u.username}`}
                        />
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-medium text-slate-100">{u.username}</span>
                      {obviousTestUser(u) && (
                        <span className="ml-2 rounded bg-slate-700/80 px-1.5 py-0.5 text-[9px] uppercase text-slate-400">
                          test
                        </span>
                      )}
                      {u.is_admin && (
                        <span className="ml-2 rounded bg-amber-800/50 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-200">
                          Admin
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-400">{u.email}</td>
                    <td className="px-4 py-3">
                      {u.is_admin ? (
                        <span className="text-amber-300">Admin</span>
                      ) : (
                        <span className="text-slate-400">User</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {u.is_admin ? (
                        <span className="text-slate-500">—</span>
                      ) : (
                        <button
                          type="button"
                          disabled={patchingId === u.id}
                          onClick={async () => {
                            setPatchingId(u.id);
                            setError(null);
                            try {
                              await api.patchAdminUser(u.id, { paid_access: !u.paid_access });
                              const next = await api.listUsers({ include_load_test: showLoadTest });
                              setUsers(next);
                            } catch (e: unknown) {
                              setError(parseApiError(e));
                            } finally {
                              setPatchingId(null);
                            }
                          }}
                          className="rounded border border-slate-600 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                        >
                          {u.paid_access ? "On" : "Off"}
                        </button>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-300">{u.credits_balance.toLocaleString()}</td>
                    <td className="px-4 py-3 text-slate-400">
                      {u.created_at
                        ? new Date(u.created_at).toLocaleDateString(undefined, {
                            year: "numeric",
                            month: "short",
                            day: "numeric",
                          })
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {u.token_version > 0 ? "Active" : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {confirmBulkOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
            <div className="w-full max-w-md rounded-lg border border-slate-600 bg-slate-900 p-5 shadow-xl">
              <p className="text-sm text-slate-100">
                Delete {selectedCount} user{selectedCount === 1 ? "" : "s"}? This action cannot be undone.
              </p>
              <p className="mt-2 text-xs text-slate-500">Your own account is never included.</p>
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  className="rounded border border-slate-600 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
                  onClick={() => setConfirmBulkOpen(false)}
                  disabled={bulkBusy}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="rounded border border-red-800 bg-red-950/50 px-3 py-1.5 text-xs font-medium text-red-200 hover:bg-red-950/70 disabled:opacity-50"
                  disabled={bulkBusy || selectedCount === 0}
                  onClick={async () => {
                    setBulkBusy(true);
                    setError(null);
                    try {
                      const ids = [...selected].filter((id) => id !== user.id);
                      const r = await api.bulkDeleteAdminUsers(ids);
                      setConfirmBulkOpen(false);
                      await refreshUsers();
                      if (r.deleted === 0 && ids.length > 0) {
                        setError("No users were deleted (invalid ids or only self-selected).");
                      }
                    } catch (e: unknown) {
                      setError(parseApiError(e));
                    } finally {
                      setBulkBusy(false);
                    }
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </Shell>
  );
}
