"use client";

import { motion, type Variants } from "framer-motion";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface GlowCardProps {
  children: ReactNode;
  className?: string;
  variants?: Variants;
  interactive?: boolean;
}

/** Glassmorphism card with a soft cyan glow on hover. */
export function GlowCard({
  children,
  className,
  variants,
  interactive = true,
}: GlowCardProps) {
  return (
    <motion.div
      variants={variants}
      whileHover={interactive ? { y: -6 } : undefined}
      transition={{ type: "spring", stiffness: 200, damping: 18 }}
      className={cn(
        "group relative overflow-hidden rounded-2xl glass p-6 shadow-soft transition-shadow duration-300 hover:shadow-glow",
        className,
      )}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-px rounded-2xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{
          background:
            "radial-gradient(400px circle at var(--x,50%) var(--y,0%), hsl(var(--brand)/0.14), transparent 60%)",
        }}
      />
      <div className="relative">{children}</div>
    </motion.div>
  );
}
