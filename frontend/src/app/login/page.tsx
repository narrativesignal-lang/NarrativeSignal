"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { api, parseApiError } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";
import { getRateLimitMessage, useI18n } from "@/lib/i18n";
import { LanguageSelector } from "@/components/LanguageSelector";

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t, locale } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const submittingRef = useRef(false);

  useEffect(() => {
    const reason = searchParams.get("reason");
    const stored = typeof sessionStorage !== "undefined" ? sessionStorage.getItem("narrative_session_expired_msg") : null;
    if (reason === "session_expired" && stored) {
      setError(stored);
      sessionStorage.removeItem("narrative_session_expired_msg");
    }
  }, [searchParams]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submittingRef.current) return;
    submittingRef.current = true;
    setError(null);
    setLoading(true);
    const loginId = email.trim();
    try {
      if (mode === "register") {
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(loginId)) {
          setError(t("auth.registerEmailInvalid"));
          setLoading(false);
          submittingRef.current = false;
          return;
        }
        await api.register(loginId, password);
      }
      const tokens = await api.login(loginId, password);
      setAccessToken(tokens.access_token);
      window.dispatchEvent(new Event("narrative:auth-change"));
      router.replace("/dashboard");
    } catch (err: unknown) {
      const raw = parseApiError(err);
      const is429 =
        (typeof err === "object" && err !== null && "status" in err && (err as { status?: number }).status === 429) ||
        raw === "__RATE_LIMIT__" ||
        /rate\s*limit/i.test(raw);
      setError(is429 ? getRateLimitMessage(locale) : raw);
    } finally {
      setLoading(false);
      submittingRef.current = false;
    }
  }

  return (
    <main className="relative mx-auto max-w-md p-6">
      <div className="absolute right-4 top-4">
        <LanguageSelector />
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-6">
        <h1 className="text-xl font-semibold">{mode === "login" ? t("auth.signIn") : t("auth.createAccount")}</h1>
        <p className="mt-1 text-sm text-slate-300">
          {t("auth.mvpCredits")}
        </p>

        <form className="mt-6 space-y-3" onSubmit={onSubmit} noValidate>
          <label className="block">
            <div className="text-xs text-slate-400">{t("auth.email")}</div>
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-slate-500"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              type={mode === "register" ? "email" : "text"}
              autoComplete="email"
            />
          </label>
          <label className="block">
            <div className="text-xs text-slate-400">{t("auth.password")}</div>
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-slate-500"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              placeholder="••••••••"
              required
            />
          </label>
          {mode === "register" ? (
            <div className="rounded border border-slate-800 bg-slate-950/50 px-2 py-2 text-xs text-slate-400">
              <p>{t("auth.registerEmailHint")}</p>
              <p className="mt-1">{t("auth.registerPasswordHint")}</p>
            </div>
          ) : null}

          {error ? <div className="rounded border border-red-900 bg-red-950/30 p-2 text-sm text-red-200">{error}</div> : null}

          <button
            className="w-full rounded bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
            disabled={loading}
          >
            {loading ? t("auth.working") : mode === "login" ? t("auth.signIn") : t("auth.registerSignIn")}
          </button>
        </form>

        <div className="mt-4 text-sm text-slate-300">
          {mode === "login" ? t("auth.noAccount") : t("auth.haveAccount")}{" "}
          <button
            type="button"
            className="text-indigo-300 hover:text-indigo-200"
            onClick={() => setMode(mode === "login" ? "register" : "login")}
          >
            {mode === "login" ? t("auth.register") : t("auth.signIn")}
          </button>
        </div>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="mx-auto max-w-md p-6"><div className="rounded-xl border border-slate-800 bg-slate-900/30 p-6 text-slate-400">Loading…</div></main>}>
      <LoginPageContent />
    </Suspense>
  );
}

