"use client";

import { Canvas } from "@react-three/fiber";
import { Line, OrbitControls } from "@react-three/drei";
import { Suspense, useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Chart3DRange, EntityChart3DData } from "@/lib/entityChart3d";
import { pathCenter, pointsToScenePath } from "@/lib/entityChart3d";

const RANGES: { key: Chart3DRange; label: string }[] = [
  { key: "1m", label: "1M" },
  { key: "3m", label: "3M" },
  { key: "6m", label: "6M" },
];

function NarrativeScene({ path }: { path: [number, number, number][] }) {
  const target = useMemo(() => {
    const c = pathCenter(path);
    return new THREE.Vector3(c[0], c[1], c[2]);
  }, [path]);

  return (
    <>
      <color attach="background" args={["#0b1120"]} />
      <ambientLight intensity={0.45} />
      <directionalLight position={[5, 8, 4]} intensity={0.88} />
      <directionalLight position={[-4, 2, -3]} intensity={0.15} color="#93c5fd" />
      <primitive object={new THREE.AxesHelper(2.4)} />
      {path.length >= 2 ? (
        <Line points={path} color="#38bdf8" lineWidth={2} />
      ) : path.length === 1 ? (
        <mesh position={path[0]}>
          <sphereGeometry args={[0.07, 20, 20]} />
          <meshStandardMaterial color="#38bdf8" emissive="#0c4a6e" emissiveIntensity={0.2} />
        </mesh>
      ) : null}
      <OrbitControls
        makeDefault
        enablePan
        enableZoom
        enableRotate
        minDistance={1.4}
        maxDistance={14}
        target={target}
      />
    </>
  );
}

/**
 * Narrative 3D: backend-driven series (search_trend 0–100 vs coverage per day).
 */
export function EntityWorkspace3DChart({ entityId }: { entityId: string }) {
  const { t } = useI18n();
  const [range, setRange] = useState<Chart3DRange>("1m");
  const [payload, setPayload] = useState<EntityChart3DData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getEntityChart3dData(entityId, range)
      .then((d) => {
        if (!cancelled) setPayload(d as EntityChart3DData);
      })
      .catch((e: { message?: string }) => {
        if (!cancelled) setError(e?.message ?? "Failed to load 3D data");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [entityId, range]);

  const path = useMemo(() => (payload?.points?.length ? pointsToScenePath(payload.points) : []), [payload]);
  const hasFullyRealInputs = payload?.source_status.search_trend === "real" && payload?.source_status.coverage_volume === "real";
  const dataState = useMemo(() => {
    if (loading) return "loading";
    if (error) return "empty";
    if (payload && !hasFullyRealInputs) return "insufficient";
    if (!payload || path.length === 0) return "empty";
    if (payload.stale) return "stale";
    if (payload.source_status.search_trend === "real") return "real";
    return "empty";
  }, [loading, error, payload, path.length, hasFullyRealInputs]);

  return (
    <div className="relative flex h-full w-full min-h-[160px] flex-col bg-[#0b1120]">
      <div className="flex flex-wrap items-center gap-1 border-b border-slate-800/80 px-2 py-1.5">
        <span className="text-[10px] text-slate-500">{t("workspace.range")}</span>
        <span
          className={`ml-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${
            dataState === "real"
              ? "bg-emerald-900/40 text-emerald-200"
              : dataState === "insufficient"
                ? "bg-amber-900/40 text-amber-200"
              : dataState === "stale"
                ? "bg-amber-900/40 text-amber-200"
                : "bg-slate-800 text-slate-300"
          }`}
        >
          {dataState}
        </span>
        {RANGES.map((r) => (
          <button
            key={r.key}
            type="button"
            onClick={() => setRange(r.key)}
            disabled={loading}
            className={`rounded px-2 py-0.5 text-[10px] font-medium ${
              range === r.key ? "bg-slate-700 text-slate-100" : "text-slate-400 hover:bg-slate-800"
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>

      <div className="relative min-h-[200px] flex-1">
        {loading ? (
          <div className="flex h-[220px] items-center justify-center text-xs text-slate-500">{t("entity.loadingSeries")}</div>
        ) : error ? (
          <div className="flex h-[220px] items-center justify-center px-3 text-center text-xs text-red-300/90">{error}</div>
        ) : payload && !hasFullyRealInputs ? (
          <div className="flex h-[220px] items-center justify-center px-4 text-center text-xs text-slate-500">
            Insufficient data: 3D path requires real search trend index and real coverage data.
          </div>
        ) : path.length === 0 ? (
          <div className="flex h-[220px] items-center justify-center px-4 text-center text-xs text-slate-500">
            {t("entity.noMetricRows")}
          </div>
        ) : (
          <Canvas
            className="h-full w-full min-h-[200px] touch-none"
            camera={{ position: [2.8, 2.2, 2.8], fov: 48, near: 0.08, far: 120 }}
            gl={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
            key={`${range}-${path.length}`}
          >
            <Suspense fallback={null}>
              <NarrativeScene path={path} />
            </Suspense>
          </Canvas>
        )}
      </div>

      <div className="relative border-t border-slate-800/80 px-2 py-1.5 text-[10px] leading-snug text-slate-500">
        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
          <span>
            Axis: <span className="text-slate-400">X time</span> · <span className="text-slate-400">Y search trend</span>{" "}
            · <span className="text-slate-400">Z coverage</span>
          </span>
        </div>
        {payload ? (
          <div className="mt-0.5 text-slate-600">
            Source: search trend ({payload.source_status.search_trend}), coverage ({payload.source_status.coverage_volume}) — relative
            index 0–100, not absolute search volume.
            {payload.last_updated_at ? ` Updated: ${payload.last_updated_at}.` : ""}
          </div>
        ) : null}
        <p className="pointer-events-none mt-1 text-slate-600">{t("workspace.rotateZoom")}</p>
      </div>
    </div>
  );
}
