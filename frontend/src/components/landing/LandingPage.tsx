"use client";

import { LanguageSelector } from "@/components/LanguageSelector";
import { useI18n } from "@/lib/i18n";
import { AuthModal } from "./AuthModal";
import { LandingBackground } from "./LandingBackground";

/* 顶部滚动条数据 */
const HEADER_TICKER_ITEMS = [
  "Fed rate outlook · NVDA +2.3% · TSLA 242 · BTC 62.4K",
  "AI chip demand · SPX 5,432 · XAU 2,350 · War risk sentiment",
  "Semiconductor cycle · ETH 3,280 · VIX 14.2 · Liquidity tightening",
  "Earnings beat · MSFT 428 · Sentiment score 0.87 · Macro regime shift",
];

function HeaderTicker() {
  const content = HEADER_TICKER_ITEMS.join("  ◆  ");
  return (
    <div
      className="header-ticker-bar w-full min-h-[42px] flex items-center border-y border-emerald-500/40 bg-slate-800/90"
      role="marquee"
      aria-label="Market data ticker"
    >
      <div className="w-full overflow-hidden">
        <div className="header-ticker flex shrink-0 whitespace-nowrap gap-12">
          <span className="font-mono text-sm text-slate-200">{content}</span>
          <span className="font-mono text-sm text-slate-200" aria-hidden>
            {content}
          </span>
        </div>
      </div>
    </div>
  );
}

/* SEO / AI 抓取关键词云 */
const SEO_KEYWORDS = [
  "Narrative Investing",
  "AI narrative intelligence",
  "Sentiment analysis",
  "Market sentiment",
  "LLM finance",
  "Quantitative finance",
  "Thematic investing",
  "Alternative data",
  "News sentiment",
  "NLP finance",
  "Alpha generation",
  "Regime detection",
  "Market trends",
  "Narrative finance",
  "Machine learning investing",
  "Sentiment tracking",
  "Entity monitoring",
  "Theme research",
];

const FEATURES = [
  {
    title: "Narrative tracking",
    description: "Monitor sentiment and narrative flow across entities, sectors, and themes.",
    icon: "📊",
  },
  {
    title: "Cross Comparison",
    description: "Build custom dashboards and research layouts with flexible charts and views.",
    icon: "🔬",
  },
  {
    title: "Reports & schedules",
    description: "Automated monitoring runs and AI-powered reports on your watchlist.",
    icon: "📈",
  },
  {
    title: "Skills Community",
    description: "Tools, indicators, and indexes from the community. Submit your own.",
    icon: "🌐",
  },
];

export function LandingPage({ onOpenAuth }: { onOpenAuth: () => void }) {
  const { t } = useI18n();
  return (
    <div className="relative min-h-screen">
      <LandingBackground />
      <div className="relative z-10 rounded-b-lg border-b border-slate-700 bg-amber-950/40 px-4 py-2 text-center text-sm text-amber-200 backdrop-blur-sm md:hidden">
        {t("landing.mobileNotice")}
      </div>
      <div className="relative z-10">
        <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-6">
          <div className="text-lg font-semibold tracking-tight text-slate-100">Narrative Investing</div>
          <div className="flex items-center gap-2">
            <LanguageSelector />
            <button
              type="button"
              onClick={onOpenAuth}
              className="rounded-lg border border-slate-600 bg-slate-800/80 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:border-slate-500 hover:bg-slate-700/80"
            >
              {t("landing.signIn")}
            </button>
          </div>
        </header>
        {/* 显眼滚动条：Logo 下方 */}
        <HeaderTicker />

        <section className="mx-auto max-w-6xl px-4 pt-16 pb-24">
          <div className="relative mx-auto max-w-3xl rounded-2xl bg-slate-950/60 px-6 py-10 backdrop-blur-md sm:px-10 sm:py-14">
            <h1 className="text-4xl font-bold tracking-tight text-slate-50 sm:text-5xl">
              {t("landing.heroTitle")}
            </h1>
            <p className="mt-6 text-lg text-slate-400">
              {t("landing.heroSub")}
            </p>
            <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
              <button
                type="button"
                onClick={onOpenAuth}
                className="rounded-lg bg-indigo-600 px-6 py-3 text-sm font-medium text-white shadow-lg shadow-indigo-500/20 transition-all hover:bg-indigo-500 hover:shadow-indigo-500/30"
              >
                {t("landing.getStarted")}
              </button>
              <button
                type="button"
                onClick={onOpenAuth}
                className="rounded-lg border border-slate-600 px-6 py-3 text-sm font-medium text-slate-300 transition-colors hover:border-slate-500 hover:text-slate-200"
              >
                {t("landing.signIn")}
              </button>
            </div>
          </div>
        </section>

        <section className="relative border-t border-slate-800/60 bg-slate-950/50 backdrop-blur-md">
          <div className="mx-auto max-w-6xl px-4 py-20">
            <h2 className="text-center text-2xl font-semibold text-slate-100">{t("landing.whatYouCanDo")}</h2>
            <p className="mx-auto mt-2 max-w-2xl text-center text-slate-400">
              {t("landing.subtitle")}
            </p>
            <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {FEATURES.map((f, i) => (
                <div
                  key={f.title}
                  className="rounded-xl border border-slate-700/50 bg-slate-950/60 p-6 backdrop-blur-sm transition-colors hover:border-slate-600/70 hover:bg-slate-950/70"
                >
                  <div className="text-2xl">{f.icon}</div>
                  <h3 className="mt-3 font-medium text-slate-100">{t(`landing.feature${i + 1}`)}</h3>
                  <p className="mt-2 text-sm text-slate-400">{t(`landing.feature${i + 1}Desc`)}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="relative overflow-hidden border-t border-slate-800/60 bg-slate-950/50 backdrop-blur-md">
          <div className="mx-auto max-w-6xl px-4 py-16">
            <div className="relative flex flex-col items-center gap-6 rounded-2xl border border-slate-700/50 bg-slate-950/80 px-8 py-12 text-center shadow-2xl backdrop-blur-md">
              {/* SEO 关键词云：模糊半透明，利于抓取 */}
              <div className="pointer-events-none absolute inset-0 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 px-6 py-4" aria-hidden>
                {SEO_KEYWORDS.map((kw) => (
                  <span
                    key={kw}
                    className="select-none text-[11px] font-medium text-slate-500/40 blur-[2px]"
                  >
                    {kw}
                  </span>
                ))}
              </div>
              <p className="relative z-10 text-lg text-slate-300">{t("landing.readyToStart")}</p>
              <button
                type="button"
                onClick={onOpenAuth}
                className="relative z-10 rounded-lg bg-indigo-600 px-8 py-3 text-sm font-medium text-white shadow-lg shadow-indigo-500/20 transition-all hover:bg-indigo-500 hover:shadow-indigo-500/30"
              >
                {t("landing.signInOrCreate")}
              </button>
            </div>
          </div>
        </section>

        <footer className="relative border-t border-slate-800/60 bg-slate-950/60 py-8 backdrop-blur-md">
          <div className="mx-auto max-w-6xl px-4 text-center text-xs text-slate-500">
            <p>{t("landing.footer")}</p>
            {/* SEO: 关键词供爬虫/AI 抓取 */}
            <nav className="sr-only" aria-label="Platform keywords">
              Narrative Investing, AI narrative intelligence, sentiment analysis, market sentiment, LLM finance,
              quantitative finance, thematic investing, alternative data, news sentiment, NLP finance, alpha generation,
              regime detection, market trends, narrative finance, machine learning investing, sentiment tracking,
              entity monitoring, theme research
            </nav>
          </div>
        </footer>
      </div>
    </div>
  );
}
