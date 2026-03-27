"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { LandingPage } from "@/components/landing/LandingPage";
import { AuthModal } from "@/components/landing/AuthModal";
import { getAccessToken, clearTokens } from "@/lib/auth";
import { api } from "@/lib/api";

export default function HomeClient() {
  const router = useRouter();
  const [authOpen, setAuthOpen] = useState(false);
  const [status, setStatus] = useState<"loading" | "unauthenticated" | "authenticated">("loading");

  useEffect(() => {
    let cancelled = false;
    const timeout = setTimeout(() => {
      if (cancelled) return;
      cancelled = true;
      setStatus("unauthenticated");
    }, 8000);
    (async () => {
      const t = getAccessToken();
      if (t) {
        clearTimeout(timeout);
        cancelled = true;
        setStatus("authenticated");
        router.replace("/dashboard");
        return;
      }
      try {
        const refreshed = await api.refresh();
        if (!cancelled) {
          localStorage.setItem("narrative_access_token", refreshed.access_token);
          setStatus("authenticated");
          router.replace("/dashboard");
        }
      } catch {
        if (!cancelled) {
          clearTokens();
          setStatus("unauthenticated");
        }
      } finally {
        clearTimeout(timeout);
        cancelled = true;
      }
    })();
    return () => {
      cancelled = true;
      clearTimeout(timeout);
    };
  }, [router]);

  if (status === "loading") {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="text-slate-400">Loading…</div>
      </main>
    );
  }

  if (status === "authenticated") {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="text-slate-400">Redirecting…</div>
      </main>
    );
  }

  return (
    <>
      <LandingPage onOpenAuth={() => setAuthOpen(true)} />
      {authOpen && <AuthModal onClose={() => setAuthOpen(false)} />}
    </>
  );
}
