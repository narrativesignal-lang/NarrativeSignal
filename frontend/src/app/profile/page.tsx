"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Shell } from "@/components/Shell";
import { api, parseApiError } from "@/lib/api";
import { clearTokens } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { useUser } from "@/lib/UserContext";

export default function ProfilePage() {
  const router = useRouter();
  const { t } = useI18n();
  const { user, loading, refetch } = useUser();
  const [profileName, setProfileName] = useState("");
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingPw, setSavingPw] = useState(false);

  useEffect(() => {
    if (user) setProfileName(user.profile_name ?? "");
  }, [user]);

  async function onSaveProfile(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    setSavingProfile(true);
    try {
      await api.patchProfile(profileName.trim());
      setMsg(t("profile.profileSaved"));
      await refetch();
    } catch (ex: unknown) {
      setErr(parseApiError(ex));
    } finally {
      setSavingProfile(false);
    }
  }

  async function onChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    if (newPw !== confirmPw) {
      setErr(t("profile.passwordMismatch"));
      return;
    }
    if (newPw.length < 8) {
      setErr(t("profile.passwordTooShort"));
      return;
    }
    setSavingPw(true);
    try {
      await api.changePassword({
        current_password: currentPw,
        new_password: newPw,
        confirm_new_password: confirmPw,
      });
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
      setMsg(t("profile.passwordChanged"));
    } catch (ex: unknown) {
      setErr(parseApiError(ex));
    } finally {
      setSavingPw(false);
    }
  }

  async function onLogOut() {
    try {
      await api.logout();
    } catch {
      // ignore
    } finally {
      clearTokens();
      router.replace("/login");
    }
  }

  if (loading) {
    return (
      <Shell>
        <div className="text-sm text-slate-400">{t("common.loading")}</div>
      </Shell>
    );
  }

  if (!user) {
    return (
      <Shell>
        <div className="space-y-3 text-sm text-slate-400">
          <p>{t("profile.loadFailed")}</p>
          <button
            type="button"
            className="rounded bg-slate-800 px-3 py-2 text-slate-100 hover:bg-slate-700"
            onClick={() => router.replace("/login")}
          >
            {t("auth.signIn")}
          </button>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="mx-auto max-w-lg space-y-10">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">{t("profile.title")}</h1>
        </div>

        {(msg || err) && (
          <div
            className={
              err
                ? "rounded border border-red-900 bg-red-950/30 p-3 text-sm text-red-200"
                : "rounded border border-emerald-900/60 bg-emerald-950/20 p-3 text-sm text-emerald-200"
            }
            role="status"
          >
            {err ?? msg}
          </div>
        )}

        <form onSubmit={onSaveProfile} className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/30 p-5">
          <div>
            <div className="text-xs text-slate-400">{t("profile.emailLabel")}</div>
            <div className="mt-1 rounded border border-slate-800 bg-slate-950/80 px-3 py-2 text-sm text-slate-300">
              {user.email}
            </div>
            <p className="mt-1 text-xs text-slate-500">{t("profile.emailReadOnlyHint")}</p>
          </div>
          <label className="block">
            <div className="text-xs text-slate-400">{t("profile.profileName")}</div>
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-slate-500"
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
              maxLength={120}
              placeholder={t("profile.profileNamePlaceholder")}
              autoComplete="name"
            />
          </label>
          <button
            type="submit"
            disabled={savingProfile}
            className="rounded bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
          >
            {savingProfile ? t("auth.working") : t("profile.saveProfile")}
          </button>
        </form>

        <form onSubmit={onChangePassword} className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/30 p-5">
          <h2 className="text-sm font-medium text-slate-200">{t("profile.changePasswordTitle")}</h2>
          <label className="block">
            <div className="text-xs text-slate-400">{t("profile.currentPassword")}</div>
            <input
              type="password"
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-slate-500"
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <label className="block">
            <div className="text-xs text-slate-400">{t("profile.newPassword")}</div>
            <input
              type="password"
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-slate-500"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              minLength={8}
              autoComplete="new-password"
              required
            />
          </label>
          <label className="block">
            <div className="text-xs text-slate-400">{t("profile.confirmPassword")}</div>
            <input
              type="password"
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-slate-500"
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              minLength={8}
              autoComplete="new-password"
              required
            />
          </label>
          <button
            type="submit"
            disabled={savingPw}
            className="rounded bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
          >
            {savingPw ? t("auth.working") : t("profile.updatePassword")}
          </button>
        </form>

        <div className="border-t border-slate-800 pt-6">
          <button
            type="button"
            onClick={onLogOut}
            className="rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"
          >
            {t("nav.logOut")}
          </button>
        </div>
      </div>
    </Shell>
  );
}
