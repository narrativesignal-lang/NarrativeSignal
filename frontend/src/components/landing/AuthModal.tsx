"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { api, parseApiError } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

export function AuthModal({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const loginId = email.trim();
    try {
      if (mode === "register") {
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(loginId)) {
          setError(t("auth.registerEmailInvalid"));
          return;
        }
        await api.register(loginId, password);
      }
      const tokens = await api.login(loginId, password);
      setAccessToken(tokens.access_token);
      window.dispatchEvent(new Event("narrative:auth-change"));
      onClose();
      router.replace("/dashboard");
    } catch (err: unknown) {
      setError(parseApiError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      data-testid="auth-modal-backdrop"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          e.preventDefault();
          e.stopPropagation();
        }
      }}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-slate-700/80 bg-slate-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-700/60 px-6 py-4">
          <h2 id="auth-modal-title" className="text-lg font-semibold text-slate-100">
            {mode === "login" ? t("auth.signIn") : t("auth.createAccount")}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <div className="p-6">
          <p className="text-sm text-slate-400">
            {t("auth.defaultPlan")}
          </p>
          <form className="mt-4 space-y-4" onSubmit={onSubmit}>
            <label className="block">
              <div className="text-xs font-medium text-slate-400">{t("auth.email")}</div>
              <input
                className="mt-1.5 w-full rounded-lg border border-slate-600 bg-slate-950 px-3 py-2.5 text-sm outline-none ring-indigo-500/50 focus:border-indigo-500 focus:ring-1"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                type={mode === "register" ? "email" : "text"}
                autoComplete="email"
              />
            </label>
            <label className="block">
              <div className="text-xs font-medium text-slate-400">{t("auth.password")}</div>
              <input
                className="mt-1.5 w-full rounded-lg border border-slate-600 bg-slate-950 px-3 py-2.5 text-sm outline-none ring-indigo-500/50 focus:border-indigo-500 focus:ring-1"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type="password"
                placeholder="••••••••"
                required
                minLength={mode === "register" ? 8 : undefined}
              />
            </label>
            {mode === "register" ? (
              <div className="rounded-lg border border-slate-700 bg-slate-950/40 px-3 py-2 text-xs text-slate-400">
                <p>{t("auth.registerEmailHint")}</p>
                <p className="mt-1">{t("auth.registerPasswordHint")}</p>
              </div>
            ) : null}
            {error ? (
              <div className="rounded-lg border border-red-900/50 bg-red-950/20 px-3 py-2 text-sm text-red-200">
                {error}
              </div>
            ) : null}
            <button
              type="submit"
              className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
              disabled={loading}
            >
              {loading ? t("auth.working") : mode === "login" ? t("auth.signIn") : t("auth.registerSignIn")}
            </button>
          </form>
          <div className="mt-4 text-center text-sm text-slate-400">
            {mode === "login" ? t("auth.noAccount") : t("auth.haveAccount")}{" "}
            <button
              type="button"
              className="text-indigo-300 hover:text-indigo-200"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setEmail("");
                setError(null);
              }}
            >
              {mode === "login" ? t("auth.register") : t("auth.signIn")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
