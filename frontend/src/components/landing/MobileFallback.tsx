"use client";

export function MobileFallback() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-6 text-center">
      <div className="text-xl font-semibold tracking-tight text-slate-100">
        Narrative Investing
      </div>
      <div className="mt-8 max-w-sm space-y-4">
        <p className="text-base text-slate-300">
          Mobile version is currently in development.
        </p>
        <p className="text-sm text-slate-400">
          Please use a desktop browser for the full experience.
        </p>
      </div>
      <div className="mt-12 rounded-full bg-slate-800/60 p-4">
        <svg
          className="h-12 w-12 text-slate-500"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
          />
        </svg>
      </div>
    </div>
  );
}
