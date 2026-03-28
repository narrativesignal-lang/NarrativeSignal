"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { LanguageSelector } from "@/components/LanguageSelector";
import { NewYorkClock } from "@/components/NewYorkClock";
import { clearTokens, getAccessToken } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { useUser } from "@/lib/UserContext";
const PUBLIC_PATHS = ["/", "/login"];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading } = useUser();
  const { t } = useI18n();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  /** Avoid hydration mismatch: server and first client paint must not branch on localStorage/window. */
  const [clientReady, setClientReady] = useState(false);
  useEffect(() => setClientReady(true), []);

  const nav = [
    { href: "/dashboard", labelKey: "nav.dashboard" },
    { href: "/research", labelKey: "nav.research" },
    { href: "/reports", labelKey: "nav.reports" },
    { href: "/schedules", labelKey: "nav.schedules" },
    { href: "/community", labelKey: "nav.community" },
    ...(user?.is_admin ? [{ href: "/admin/users", labelKey: "nav.adminUsers" as const }] : []),
  ];

  const navLinkClass = (href: string) =>
    "block rounded px-3 py-2 text-sm " +
    (pathname === href ? "bg-slate-800 text-slate-50" : "text-slate-300 hover:bg-slate-800/60");

  // Redirect only when there is no access token. Avoid redirect loops when /me is slow or
  // transiently fails but the JWT is still valid (previous logic also treated !user as unauth).
  useEffect(() => {
    if (loading) return;
    const isPublic = PUBLIC_PATHS.includes(pathname);
    if (isPublic) return;
    if (getAccessToken()) return;
    const msg = typeof sessionStorage !== "undefined" ? sessionStorage.getItem("narrative_session_expired_msg") : null;
    router.replace(msg ? "/login?reason=session_expired" : "/");
  }, [pathname, loading, router]);

  const isPublicPath = PUBLIC_PATHS.includes(pathname);

  if (!isPublicPath && !clientReady) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-sm text-slate-400">{t("common.loading")}</div>
      </div>
    );
  }

  if (!isPublicPath && !loading && !getAccessToken()) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-sm text-slate-400">{t("common.redirecting")}</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-slate-800 bg-slate-950/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-3 py-2.5 sm:px-4 sm:py-3">
          <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-4">
            {/* Mobile menu button */}
            <button
              type="button"
              onClick={() => setMobileNavOpen((o) => !o)}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded border border-slate-700 bg-slate-900/60 text-slate-300 hover:bg-slate-800 md:hidden"
              aria-label={mobileNavOpen ? t("nav.menuCloseAria") : t("nav.menuOpenAria")}
              aria-expanded={mobileNavOpen}
            >
              {mobileNavOpen ? (
                <span className="text-lg leading-none">×</span>
              ) : (
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              )}
            </button>
            <div className="min-w-0 truncate text-sm font-semibold tracking-wide text-slate-100">
              Narrative Investing
            </div>
            {/* Desktop nav */}
            <nav className="hidden gap-2 text-sm text-slate-300 md:flex">
              {nav.map((i) => (
                <Link key={i.href} href={i.href} className={navLinkClass(i.href)}>
                  {t(i.labelKey)}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
            <NewYorkClock />
            <LanguageSelector />
            {user?.is_admin && (
              <span className="hidden rounded bg-amber-900/60 px-2 py-0.5 text-xs text-amber-200 sm:inline">
                {t("nav.admin")}
              </span>
            )}
            <Link
              href="/profile"
              className="rounded bg-slate-800 px-2.5 py-1.5 text-sm text-slate-100 hover:bg-slate-700 sm:px-3"
            >
              {t("nav.profile")}
            </Link>
          </div>
        </div>
        {/* Mobile nav dropdown */}
        {mobileNavOpen ? (
          <div className="border-t border-slate-800 bg-slate-900/95 px-3 py-2 md:hidden">
            <nav className="flex flex-col gap-0.5">
              {nav.map((i) => (
                <Link
                  key={i.href}
                  href={i.href}
                  onClick={() => setMobileNavOpen(false)}
                  className={navLinkClass(i.href)}
                >
                  {t(i.labelKey)}
                </Link>
              ))}
            </nav>
          </div>
        ) : null}
      </header>
      <main className="mx-auto min-w-0 max-w-6xl overflow-x-hidden px-3 py-4 sm:px-4 sm:py-6">{children}</main>
    </div>
  );
}

