"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Produces gently fluctuating values around each base (mock realtime gauges).
 */
export function useJitter(
  bases: { id: string; base: number }[],
  amplitude = 6,
  intervalMs = 2000,
) {
  const [values, setValues] = useState<Record<string, number>>(() =>
    Object.fromEntries(bases.map((b) => [b.id, b.base])),
  );
  const ref = useRef(bases);
  ref.current = bases;

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    const id = setInterval(() => {
      setValues(() =>
        Object.fromEntries(
          ref.current.map((b) => {
            const delta = (Math.random() - 0.5) * amplitude;
            const val = Math.max(2, Math.min(99, b.base + delta));
            return [b.id, Math.round(val)];
          }),
        ),
      );
    }, intervalMs);
    return () => clearInterval(id);
  }, [amplitude, intervalMs]);

  return values;
}
