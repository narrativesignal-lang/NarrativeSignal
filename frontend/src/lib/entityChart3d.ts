/**
 * Narrative 3D chart: API-aligned types and scene mapping (no random mock data here).
 */

export type Chart3DRange = "1m" | "3m" | "6m";

export type EntityChart3DPoint = {
  date: string;
  search_trend: number;
  coverage_volume: number;
};

export type EntityChart3DData = {
  entity_id: string;
  range: string;
  mode: string;
  points: EntityChart3DPoint[];
  last_updated_at?: string | null;
  stale?: boolean;
  source_status: {
    search_trend: "mock" | "real" | "mock_fallback";
    coverage_volume: "mock" | "real";
  };
};

/**
 * Map API points to scene coordinates:
 * X = time index (chronological), Y = search_trend (0–100 → height), Z = coverage (normalized).
 */
export function pointsToScenePath(points: EntityChart3DPoint[]): [number, number, number][] {
  if (!points.length) return [];
  const maxCov = Math.max(...points.map((p) => p.coverage_volume), 1e-6);
  const n = points.length;
  return points.map((p, i) => {
    const x = n <= 1 ? 0 : (i / (n - 1)) * 4 - 2;
    const y = (p.search_trend / 100) * 2;
    const z = (p.coverage_volume / maxCov) * 4 - 2;
    return [x, y, z] as [number, number, number];
  });
}

export function pathCenter(pts: [number, number, number][]): [number, number, number] {
  if (!pts.length) return [0, 0, 0];
  let sx = 0,
    sy = 0,
    sz = 0;
  for (const [x, y, z] of pts) {
    sx += x;
    sy += y;
    sz += z;
  }
  const n = pts.length;
  return [sx / n, sy / n, sz / n];
}
