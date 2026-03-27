"use client";

import { useEffect, useState } from "react";

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

export default function AdminUsersPage() {
  const { user, loading: userLoading } = useUser();
  const { t } = useI18n();
  const [users, setUsers] = useState<UserRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [patchingId, setPatchingId] = useState<string | null>(null);

  useEffect(() => {
    if (userLoading) return;
    if (!user?.is_admin) {
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .listUsers()
      .then(setUsers)
      .catch((e: unknown) => setError(parseApiError(e)))
      .finally(() => setLoading(false));
  }, [user?.is_admin, userLoading, user?.id]);

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
      <div className="mx-auto max-w-4xl p-6">
        <h1 className="text-xl font-semibold text-slate-100">{t("nav.admin")} — Users</h1>
        <p className="mt-1 text-sm text-slate-400">All registered users ({users.length})</p>

        {loading ? (
          <p className="mt-6 text-sm text-slate-500">Loading…</p>
        ) : error ? (
          <div className="mt-6 rounded border border-red-900/50 bg-red-950/20 px-4 py-2 text-sm text-red-200">
            {error}
          </div>
        ) : (
          <div className="mt-6 overflow-x-auto rounded-lg border border-slate-700 bg-slate-900/50">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700 bg-slate-800/60">
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
                    <td className="px-4 py-3">
                      <span className="font-medium text-slate-100">{u.username}</span>
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
                              const next = await api.listUsers();
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
      </div>
    </Shell>
  );
}
