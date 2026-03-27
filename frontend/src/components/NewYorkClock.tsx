"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/lib/i18n";

const NY_TZ = "America/New_York";

/** Live clock for US Eastern (New York). Shown in header; schedules use this timezone on the server. */
export function NewYorkClock() {
  const { t } = useI18n();
  const [line, setLine] = useState("");

  useEffect(() => {
    function tick() {
      const d = new Date();
      const datePart = new Intl.DateTimeFormat("en-US", {
        timeZone: NY_TZ,
        weekday: "short",
        month: "short",
        day: "numeric",
      }).format(d);
      const timePart = new Intl.DateTimeFormat("en-US", {
        timeZone: NY_TZ,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      }).format(d);
      const tzPart = new Intl.DateTimeFormat("en-US", {
        timeZone: NY_TZ,
        timeZoneName: "short",
      })
        .formatToParts(d)
        .find((p) => p.type === "timeZoneName")?.value;
      setLine(`${datePart} · ${timePart}${tzPart ? ` ${tzPart}` : ""}`);
    }
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <span
      className="inline-block max-w-[min(12rem,32vw)] truncate font-mono text-[10px] text-slate-500 tabular-nums sm:max-w-none sm:text-xs"
      title={t("nav.nyClockTitle")}
    >
      <span className="text-slate-600">{t("nav.nyClockPrefix")}</span> {line}
    </span>
  );
}
