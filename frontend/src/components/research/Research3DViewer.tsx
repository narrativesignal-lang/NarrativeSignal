"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

type Variant = "narrative" | "derivative";

const AXES_LABELS: Record<Variant, { x: string; y: string; z: string }> = {
  narrative: { x: "Search Volume", y: "Coverage Volume", z: "Time" },
  derivative: { x: "Search Momentum", y: "Coverage Momentum", z: "Market Confirmation" },
};

const DEFAULT_CAMERA_POSITION = { x: 2, y: 1.5, z: 2 };

export function Research3DViewer({
  variant,
  hasContext,
  onRemove,
  onMoveUp,
  onMoveDown,
}: {
  variant: Variant;
  hasContext?: boolean;
  onRemove?: () => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [resetKey, setResetKey] = useState(0);
  const labels = AXES_LABELS[variant];

  useEffect(() => {
    const container = containerRef.current;
    if (!container || typeof window === "undefined") return;

    const width = container.clientWidth;
    const height = Math.max(200, container.clientHeight);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0f172a);

    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
    camera.position.set(DEFAULT_CAMERA_POSITION.x, DEFAULT_CAMERA_POSITION.y, DEFAULT_CAMERA_POSITION.z);
    camera.lookAt(0, 0, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.screenSpacePanning = false;
    controls.minDistance = 0.5;
    controls.maxDistance = 20;

    const axesHelper = new THREE.AxesHelper(1.2);
    scene.add(axesHelper);

    const gridHelper = new THREE.GridHelper(2, 8, 0x334155, 0x1e293b);
    scene.add(gridHelper);

    const geometry = new THREE.SphereGeometry(0.04, 8, 8);
    const material = new THREE.MeshBasicMaterial({ color: 0x818cf8 });
    const meshes: THREE.Mesh[] = [];
    for (let i = 0; i < 40; i++) {
      const t = (i / 40) * Math.PI * 2;
      const x = 0.4 * Math.cos(t) + (Math.random() - 0.5) * 0.3;
      const y = 0.3 * Math.sin(t * 1.3) + (Math.random() - 0.5) * 0.2;
      const z = (i / 40) * 0.8 - 0.4 + (Math.random() - 0.5) * 0.2;
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.set(x, y, z);
      scene.add(mesh);
      meshes.push(mesh);
    }

    let animationId: number;
    function animate() {
      animationId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }
    animate();

    function onResize() {
      if (!container) return;
      const w = container.clientWidth;
      const h = Math.max(200, container.clientHeight);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    }
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(animationId);
      controls.dispose();
      renderer.dispose();
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement);
      geometry.dispose();
      material.dispose();
    };
  }, [variant, resetKey]);

  return (
    <div className="relative flex h-full min-h-[280px] flex-col rounded-lg border border-slate-700 bg-slate-900/50 overflow-hidden">
      <div className="flex items-center justify-between gap-1 p-2 border-b border-slate-700/60">
        <span className="text-xs font-medium text-slate-400">
          {variant === "narrative" ? "3D Narrative Space" : "3D Derivative Space"}
        </span>
        <div className="flex items-center gap-0.5">
          {onMoveUp && (
            <button type="button" onClick={onMoveUp} className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300" title="Move up">↑</button>
          )}
          {onMoveDown && (
            <button type="button" onClick={onMoveDown} className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300" title="Move down">↓</button>
          )}
          {onRemove && (
            <button type="button" onClick={onRemove} className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-red-300" title="Remove">×</button>
          )}
        </div>
      </div>
      <div ref={containerRef} className="flex-1 min-h-[200px] w-full" />
      <div className="flex items-center justify-between px-2 py-1.5 border-t border-slate-700/60 bg-slate-900/60">
        <span className="text-[10px] text-slate-500">
          X: {labels.x} · Y: {labels.y} · Z: {labels.z}
        </span>
        <button
          type="button"
          onClick={() => setResetKey((k) => k + 1)}
          className="rounded px-2 py-0.5 text-xs text-slate-400 hover:bg-slate-700 hover:text-slate-200"
        >
          Reset view
        </button>
      </div>
      {!hasContext && (
        <div className="absolute bottom-8 left-2 rounded bg-amber-900/40 px-2 py-0.5 text-[10px] text-amber-200/90">
          Demo · Connect research universe for live data
        </div>
      )}
    </div>
  );
}
