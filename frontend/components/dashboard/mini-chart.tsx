"use client";

import { useId } from "react";

import type { TrendPoint } from "@/types";

interface MiniChartProps {
  data: TrendPoint[];
  variant?: "area" | "bar";
  height?: number;
}

/** Dependency-free SVG chart used across the dashboard preview. */
export function MiniChart({ data, variant = "area", height = 120 }: MiniChartProps) {
  const gradientId = useId();
  const width = 320;
  const pad = 8;
  const max = Math.max(...data.map((d) => d.value)) || 1;
  const stepX = (width - pad * 2) / Math.max(data.length - 1, 1);

  const points = data.map((d, i) => ({
    x: pad + i * stepX,
    y: height - pad - (d.value / max) * (height - pad * 2),
  }));

  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");
  const areaPath = `${linePath} L${points[points.length - 1].x},${height - pad} L${points[0].x},${height - pad} Z`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-full w-full"
      preserveAspectRatio="none"
      role="img"
      aria-label="Trend chart"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="hsl(var(--brand))" stopOpacity="0.35" />
          <stop offset="100%" stopColor="hsl(var(--brand))" stopOpacity="0" />
        </linearGradient>
      </defs>

      {variant === "area" ? (
        <>
          <path d={areaPath} fill={`url(#${gradientId})`} />
          <path
            d={linePath}
            fill="none"
            stroke="hsl(var(--brand))"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {points.map((p, i) => (
            <circle key={i} cx={p.x} cy={p.y} r="2.5" fill="hsl(var(--brand))" />
          ))}
        </>
      ) : (
        data.map((d, i) => {
          const barW = stepX * 0.5;
          const h = (d.value / max) * (height - pad * 2);
          return (
            <rect
              key={i}
              x={pad + i * stepX - barW / 2}
              y={height - pad - h}
              width={barW}
              height={h}
              rx="3"
              fill="hsl(var(--brand))"
              opacity={0.85}
            />
          );
        })
      )}
    </svg>
  );
}
