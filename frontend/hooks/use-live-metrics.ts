"use client";

import { useEffect, useRef, useState } from "react";

import type { LiveMetric } from "@/types";

/**
 * Returns current values for a set of metrics. Metrics flagged `live` grow by a
 * small random amount on an interval (mock "real-time" feel). Starts from the
 * base values to avoid hydration mismatches.
 */
export function useLiveMetrics(metrics: LiveMetric[], intervalMs = 2500) {
  const [values, setValues] = useState<Record<string, number>>(() =>
    Object.fromEntries(metrics.map((m) => [m.id, m.base])),
  );
  const metricsRef = useRef(metrics);
  metricsRef.current = metrics;

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    const id = setInterval(() => {
      setValues((prev) => {
        const next = { ...prev };
        for (const m of metricsRef.current) {
          if (m.live && m.drift > 0) {
            next[m.id] = prev[m.id] + Math.round(Math.random() * m.drift) + 1;
          }
        }
        return next;
      });
    }, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return values;
}
