const envInt = (key: string, fallback: number): number => {
  const raw = import.meta.env[key]
  if (raw === undefined || raw === '') return fallback
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? n : fallback
}

export const POLL = {
  FAST: envInt('VITE_POLL_FAST_MS', 2_000),
  NORMAL: envInt('VITE_POLL_NORMAL_MS', 10_000),
  SLOW: envInt('VITE_POLL_SLOW_MS', 30_000),
  VERY_SLOW: envInt('VITE_POLL_VERY_SLOW_MS', 60_000),
} as const
