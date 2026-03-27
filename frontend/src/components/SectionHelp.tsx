"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useI18n } from "@/lib/i18n";

type SectionHelpProps = {
  titleKey: string;
  bodyKey: string;
  className?: string;
};

/** Compact “?” control: opens a short popover (what it is + how to use). Rendered in a portal so it is not clipped. */
export function SectionHelp({ titleKey, bodyKey, className }: SectionHelpProps) {
  const { t } = useI18n();
  const id = useId();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [popoverPos, setPopoverPos] = useState<{ top: number; left: number; width: number } | null>(null);

  const close = useCallback(() => setOpen(false), []);

  const updatePos = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const maxW = 288;
    const pad = 8;
    const width = Math.min(maxW, window.innerWidth - pad * 2);
    let left = r.left;
    if (left + width > window.innerWidth - pad) {
      left = Math.max(pad, window.innerWidth - width - pad);
    }
    setPopoverPos({ top: r.bottom + 6, left, width });
  }, []);

  useLayoutEffect(() => {
    if (!open) return;
    updatePos();
    window.addEventListener("scroll", updatePos, true);
    window.addEventListener("resize", updatePos);
    return () => {
      window.removeEventListener("scroll", updatePos, true);
      window.removeEventListener("resize", updatePos);
    };
  }, [open, updatePos]);

  useEffect(() => {
    if (!open) return;
    function onDocMouseDown(e: MouseEvent) {
      const node = e.target as Node;
      if (rootRef.current?.contains(node)) return;
      if (popoverRef.current?.contains(node)) return;
      close();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  const popover =
    open && popoverPos && typeof document !== "undefined" ? (
      <div
        ref={popoverRef}
        id={`${id}-help`}
        role="dialog"
        aria-label={t("help.buttonAria")}
        className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2.5 text-left shadow-xl ring-1 ring-black/20"
        style={{
          position: "fixed",
          top: popoverPos.top,
          left: popoverPos.left,
          width: popoverPos.width,
          zIndex: 9999,
        }}
      >
        <div className="text-xs font-semibold text-slate-100">{t(titleKey)}</div>
        <p className="mt-1.5 text-[11px] leading-relaxed text-slate-400">{t(bodyKey)}</p>
      </div>
    ) : null;

  return (
    <div className={["relative inline-flex shrink-0 align-middle", className].filter(Boolean).join(" ")} ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded border border-slate-600 bg-slate-800/80 px-1 text-[10px] font-semibold leading-none text-slate-400 hover:border-slate-500 hover:bg-slate-700/90 hover:text-slate-200"
        aria-expanded={open}
        aria-controls={`${id}-help`}
        aria-label={t("help.buttonAria")}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        ?
      </button>
      {popover ? createPortal(popover, document.body) : null}
    </div>
  );
}

/** Flex row: heading + optional help (for section titles). */
export function HeadingWithHelp({
  title,
  helpTitleKey,
  helpBodyKey,
  className,
}: {
  title: string;
  helpTitleKey: string;
  helpBodyKey: string;
  className?: string;
}) {
  return (
    <div className={["flex items-center gap-1.5", className].filter(Boolean).join(" ")}>
      <span>{title}</span>
      <SectionHelp titleKey={helpTitleKey} bodyKey={helpBodyKey} />
    </div>
  );
}
