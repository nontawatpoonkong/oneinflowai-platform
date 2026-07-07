"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { fadeUp } from "@/lib/animations";
import { cn } from "@/lib/utils";

interface MetricTileProps {
  icon: LucideIcon;
  label: string;
  children: ReactNode;
  hint?: string;
  className?: string;
}

/** Reusable stat tile: icon + animated value + label. */
export function MetricTile({
  icon: Icon,
  label,
  children,
  hint,
  className,
}: MetricTileProps) {
  return (
    <motion.div
      variants={fadeUp}
      className={cn(
        "glass flex flex-col gap-3 rounded-2xl p-6 shadow-soft",
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <span className="grid size-10 place-items-center rounded-xl bg-brand/10 text-brand">
          <Icon className="size-5" />
        </span>
        {hint ? (
          <span className="text-xs font-medium text-muted-foreground">{hint}</span>
        ) : null}
      </div>
      <div className="text-3xl font-semibold tracking-tight">{children}</div>
      <p className="text-sm text-muted-foreground">{label}</p>
    </motion.div>
  );
}
