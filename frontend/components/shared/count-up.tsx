"use client";

import { animate, useInView, useMotionValue } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { formatNumber } from "@/utils/format";

interface CountUpProps {
  value: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  format?: (n: number) => string;
  duration?: number;
  className?: string;
}

/**
 * Eased number animation. Animates from 0 -> value when scrolled into view,
 * then re-animates smoothly whenever `value` changes (live metrics).
 */
export function CountUp({
  value,
  decimals = 0,
  prefix = "",
  suffix = "",
  format,
  duration = 1.6,
  className,
}: CountUpProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const motionValue = useMotionValue(0);
  const started = useRef(false);
  const [display, setDisplay] = useState(0);

  useEffect(() => motionValue.on("change", setDisplay), [motionValue]);

  useEffect(() => {
    if (!inView) return;
    const controls = animate(motionValue, value, {
      duration: started.current ? 0.9 : duration,
      ease: "easeOut",
    });
    started.current = true;
    return () => controls.stop();
  }, [inView, value, duration, motionValue]);

  const text = format
    ? format(display)
    : `${prefix}${formatNumber(Number(display.toFixed(decimals)))}${suffix}`;

  return (
    <span ref={ref} className={className}>
      {text}
    </span>
  );
}
