/**
 * Shared research data / math foundation for charts and 3D tools.
 * Ready for: search volume, coverage, price, order flow providers.
 */

export function normalize(values: number[]): number[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  return values.map((v) => (v - min) / range);
}

export function zscore(values: number[]): number[] {
  if (values.length === 0) return [];
  const n = values.length;
  const mean = values.reduce((a, b) => a + b, 0) / n;
  const variance = values.reduce((sum, v) => sum + (v - mean) ** 2, 0) / n;
  const std = Math.sqrt(variance) || 1;
  return values.map((v) => (v - mean) / std);
}

export function movingAverage(values: number[], window: number): number[] {
  if (values.length === 0 || window < 1) return [];
  const out: number[] = [];
  for (let i = 0; i < values.length; i++) {
    const start = Math.max(0, i - window + 1);
    const slice = values.slice(start, i + 1);
    out.push(slice.reduce((a, b) => a + b, 0) / slice.length);
  }
  return out;
}

export function ema(values: number[], span: number): number[] {
  if (values.length === 0 || span < 1) return [];
  const alpha = 2 / (span + 1);
  const out: number[] = [values[0]];
  for (let i = 1; i < values.length; i++) {
    out.push(alpha * values[i] + (1 - alpha) * out[i - 1]);
  }
  return out;
}

export function momentum(values: number[], period: number = 1): number[] {
  if (values.length === 0) return [];
  const out: number[] = [];
  for (let i = 0; i < values.length; i++) {
    const prev = i >= period ? values[i - period] : values[0];
    out.push(values[i] - prev);
  }
  return out;
}

export function acceleration(values: number[], period: number = 1): number[] {
  const mom = momentum(values, period);
  return momentum(mom, period);
}

export function ratio(a: number[], b: number[]): number[] {
  const len = Math.min(a.length, b.length);
  const out: number[] = [];
  for (let i = 0; i < len; i++) {
    out.push(b[i] === 0 ? 0 : a[i] / b[i]);
  }
  return out;
}

export function correlation(x: number[], y: number[]): number {
  const n = Math.min(x.length, y.length);
  if (n < 2) return 0;
  const mx = x.slice(0, n).reduce((a, b) => a + b, 0) / n;
  const my = y.slice(0, n).reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let dx2 = 0;
  let dy2 = 0;
  for (let i = 0; i < n; i++) {
    const dx = x[i] - mx;
    const dy = y[i] - my;
    num += dx * dy;
    dx2 += dx * dx;
    dy2 += dy * dy;
  }
  const den = Math.sqrt(dx2 * dy2) || 1;
  return num / den;
}

export function lagCorrelation(x: number[], y: number[], maxLag: number): number[] {
  const out: number[] = [];
  for (let lag = 0; lag <= maxLag; lag++) {
    const xSlice = x.slice(0, x.length - lag);
    const ySlice = y.slice(lag);
    out.push(correlation(xSlice, ySlice));
  }
  return out;
}

/** Build 3D points for Narrative Space: x = search volume, y = coverage volume, z = time index. */
export function build3dPointsNarrative(
  searchVolume: number[],
  coverageVolume: number[],
  options?: { normalizeAxis?: boolean }
): Array<{ x: number; y: number; z: number }> {
  const n = Math.min(searchVolume.length, coverageVolume.length);
  const points: Array<{ x: number; y: number; z: number }> = [];
  const useNorm = options?.normalizeAxis !== false;
  const sx = useNorm ? zscore(searchVolume.slice(0, n)) : searchVolume.slice(0, n);
  const sy = useNorm ? zscore(coverageVolume.slice(0, n)) : coverageVolume.slice(0, n);
  for (let i = 0; i < n; i++) {
    points.push({ x: sx[i], y: sy[i], z: i / Math.max(1, n - 1) });
  }
  return points;
}

/** Build 3D points for Derivative/Quadrant: x = search momentum, y = coverage momentum, z = market confirmation. */
export function build3dPointsDerivative(
  searchSeries: number[],
  coverageSeries: number[],
  marketSeries: number[],
  period: number = 1
): Array<{ x: number; y: number; z: number }> {
  const searchMom = momentum(searchSeries, period);
  const coverageMom = momentum(coverageSeries, period);
  const marketMom = momentum(marketSeries, period);
  const n = Math.min(searchMom.length, coverageMom.length, marketMom.length);
  const points: Array<{ x: number; y: number; z: number }> = [];
  const x = zscore(searchMom.slice(0, n));
  const y = zscore(coverageMom.slice(0, n));
  const z = zscore(marketMom.slice(0, n));
  for (let i = 0; i < n; i++) {
    points.push({ x: x[i], y: y[i], z: z[i] });
  }
  return points;
}
