/**
 * Best-effort Next.js cache cleanup. Never exits with failure — avoids killing `pnpm run dev`
 * when `.next` is on a Docker volume / locked (EBUSY).
 *
 * Order: remove smaller subtrees first (often where stale webpack chunks live), then whole `.next`.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", ".next");

/** Codes that mean "skip, don't crash" */
function isBusyOrLocked(err) {
  if (!err || !err.code) return false;
  return ["EBUSY", "EPERM", "EACCES", "ENOTEMPTY", "EMFILE"].includes(err.code);
}

function safeRmDir(dir, label) {
  try {
    if (!fs.existsSync(dir)) return true;
    fs.rmSync(dir, { recursive: true, force: true });
    console.log(`[clean-next] removed ${label}`);
    return true;
  } catch (err) {
    if (err.code === "ENOENT") return true;
    if (isBusyOrLocked(err)) {
      console.warn(`[clean-next] skipped ${label} (${err.code}): ${path.relative(process.cwd(), dir)}`);
      return false;
    }
    console.warn(`[clean-next] skipped ${label} (${err.code}):`, err.message);
    return false;
  }
}

function main() {
  if (!fs.existsSync(root)) {
    console.log("[clean-next] no .next directory");
    return;
  }

  // Targeted dirs first (reduces lock surface; helps stale chunk issues)
  const subdirs = [
    ["cache", "cache"],
    ["server", "server"],
    ["static", "static"],
  ];
  for (const [rel, label] of subdirs) {
    safeRmDir(path.join(root, rel), `.next/${label}`);
  }

  // Whole tree last (may still be EBUSY on Docker bind + volume)
  safeRmDir(root, ".next (full)");

  console.log("[clean-next] done (non-fatal — starting next dev is OK)");
}

try {
  main();
} catch (err) {
  console.warn("[clean-next] unexpected (ignored):", err && err.message);
}

process.exit(0);
