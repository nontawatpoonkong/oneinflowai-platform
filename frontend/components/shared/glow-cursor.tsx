"use client";

import { motion, useMotionValue, useSpring } from "framer-motion";
import { useEffect, useState } from "react";

import { useMediaQuery } from "@/hooks/use-media-query";

/**
 * Soft cyan glow that trails the cursor. Desktop + fine-pointer only, fully
 * decorative (pointer-events: none, aria-hidden) and disabled for reduced
 * motion — never interferes with accessibility.
 */
export function GlowCursor() {
  const finePointer = useMediaQuery("(pointer: fine)");
  const [enabled, setEnabled] = useState(false);

  const x = useMotionValue(-100);
  const y = useMotionValue(-100);
  const springX = useSpring(x, { stiffness: 300, damping: 30, mass: 0.4 });
  const springY = useSpring(y, { stiffness: 300, damping: 30, mass: 0.4 });

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!finePointer || reduce) {
      setEnabled(false);
      return;
    }
    setEnabled(true);
    const move = (e: MouseEvent) => {
      x.set(e.clientX);
      y.set(e.clientY);
    };
    window.addEventListener("mousemove", move);
    return () => window.removeEventListener("mousemove", move);
  }, [finePointer, x, y]);

  if (!enabled) return null;

  return (
    <motion.div
      aria-hidden
      style={{ left: springX, top: springY }}
      className="pointer-events-none fixed z-[9999] hidden -translate-x-1/2 -translate-y-1/2 md:block"
    >
      <div className="size-64 rounded-full bg-brand/10 blur-3xl" />
    </motion.div>
  );
}
