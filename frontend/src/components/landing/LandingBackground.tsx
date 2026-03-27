"use client";

/* 新闻 / News */
const NEWS_ROW = [
  "Fed signals rate cut in Q3",
  "AI chip demand accelerating",
  "Oil spikes on supply concerns",
  "Semiconductor cycle turning",
  "War risk sentiment rising",
  "Liquidity tightening globally",
  "Earnings beat expectations",
  "Credit spread widens",
];

/* 价格 / Prices */
const PRICE_ROW = [
  "NVDA 138.52 +2.3%",
  "BTC 62,400",
  "ETH 3,280",
  "TSLA 242",
  "SPX 5,432",
  "VIX 14.2",
  "XAU 2,350",
  "MSFT 428",
];

/* 关键词 / Keywords */
const KEYWORD_ROW = [
  "AI",
  "GPU",
  "inflation",
  "macro",
  "sentiment",
  "narrative",
  "momentum",
  "liquidity",
  "regime",
  "yield curve",
  "risk-on",
];

/* 微型图表占位 (sparkline-like) */
function MiniSparkline({ delay = "" }: { delay?: string }) {
  return (
    <svg className={`landing-sparkline h-5 w-20 opacity-80 ${delay}`} viewBox="0 0 64 16" preserveAspectRatio="none">
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="0.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-emerald-500/60"
        d="M0,12 L8,10 L16,8 L24,6 L32,4 L40,8 L48,6 L56,4 L64,2"
      />
    </svg>
  );
}

function TickerRow({
  items,
  direction = "ltr",
  className = "text-slate-500/70",
}: {
  items: string[];
  direction?: "ltr" | "rtl";
  className?: string;
}) {
  const content = items.join("  ·  ");
  return (
    <div className="landing-ticker-wrapper flex overflow-hidden whitespace-nowrap">
      <div className={`landing-ticker flex shrink-0 gap-8 ${direction === "rtl" ? "landing-ticker-rtl" : ""}`}>
        <span className={className}>{content}</span>
        <span className={className} aria-hidden>
          {content}
        </span>
      </div>
    </div>
  );
}

export function LandingBackground() {
  return (
    <div className="landing-bg fixed inset-0 -z-20 overflow-hidden bg-slate-950">
      {/* Layer A: 深色基底 + 渐变光晕 */}
      <div className="absolute inset-0 bg-gradient-to-br from-slate-950 via-slate-900/95 to-slate-950" />
      <div className="landing-gradient-shift absolute inset-0" />

      {/* Layer B: 数据流 - 新闻、价格、关键词（更明显） */}
      <div className="absolute inset-0 flex flex-col justify-around py-16 opacity-100">
        <TickerRow items={NEWS_ROW} direction="ltr" className="text-slate-200 text-sm" />
        <TickerRow items={PRICE_ROW} direction="rtl" className="text-emerald-400 text-xs font-mono" />
        <TickerRow items={KEYWORD_ROW} direction="ltr" className="text-slate-300 text-xs" />
        <TickerRow items={NEWS_ROW.slice(0, 6)} direction="rtl" className="text-slate-400 text-xs" />
      </div>

      {/* 微型图表点缀 */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-around opacity-70">
        <div className="mt-48">
          <MiniSparkline delay="landing-sparkline-delay" />
        </div>
        <div className="-mt-32">
          <MiniSparkline delay="landing-sparkline-delay-2" />
        </div>
        <div className="mt-64">
          <MiniSparkline delay="landing-sparkline-delay-3" />
        </div>
      </div>

      {/* Layer C: Hacker 终端风格 */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden opacity-[0.35]">
        <div className="landing-terminal absolute left-[5%] top-[12%] font-mono text-[10px] text-emerald-400">
          0x7f3a2b...
        </div>
        <div className="landing-terminal landing-terminal-2 absolute right-[8%] top-[22%] font-mono text-[10px] text-emerald-400">
          parse_signal() → 0.87
        </div>
        <div className="landing-terminal landing-terminal-3 absolute left-[12%] bottom-[40%] font-mono text-[10px] text-emerald-400">
          {">>"} fetch_narrative
        </div>
        <div className="landing-terminal landing-terminal-4 absolute right-[6%] bottom-[18%] font-mono text-[10px] text-emerald-400">
          latency: 12ms
        </div>
        <div className="landing-terminal landing-terminal-5 absolute left-[18%] top-[48%] font-mono text-[10px] text-emerald-400">
          sentiment_agg
        </div>
        <div className="landing-terminal landing-terminal-6 absolute right-[15%] top-[58%] font-mono text-[10px] text-emerald-400">
          weight: 0.42
        </div>
        <div className="landing-terminal landing-terminal-7 absolute left-[25%] bottom-[25%] font-mono text-[10px] text-emerald-400">
          trend_up
        </div>
        <div className="landing-terminal landing-terminal-8 absolute right-[22%] top-[35%] font-mono text-[10px] text-emerald-400">
          [OK] sync
        </div>
      </div>

      {/* 半透明遮罩：保持前景文案清晰，但让背景数据流可见 */}
      <div
        className="absolute inset-0 bg-gradient-to-b from-slate-950/55 via-slate-950/25 to-slate-950/60"
        aria-hidden
      />
    </div>
  );
}
