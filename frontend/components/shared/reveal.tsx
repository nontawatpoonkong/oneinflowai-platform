"use client";

import { motion, type Variants } from "framer-motion";
import type { ReactNode } from "react";

import { fadeUp, staggerContainer, VIEWPORT } from "@/lib/animations";
import { cn } from "@/lib/utils";

interface RevealProps {
  children: ReactNode;
  className?: string;
  variants?: Variants;
  stagger?: boolean;
}

/** Scroll-reveal wrapper. Use `stagger` to animate children in sequence. */
export function Reveal({ children, className, variants, stagger }: RevealProps) {
  return (
    <motion.div
      variants={variants ?? (stagger ? staggerContainer : fadeUp)}
      initial="hidden"
      whileInView="visible"
      viewport={VIEWPORT}
      className={cn(className)}
    >
      {children}
    </motion.div>
  );
}
