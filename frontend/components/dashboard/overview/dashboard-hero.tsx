"use client";

import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { scaleIn } from "@/lib/animations";
import { cn } from "@/lib/utils";

/** Lightweight animated "AI working" illustration (no Lottie). */
function HeroIllustration() {
  const rings = ["inset-0", "inset-3", "inset-6"];
  return (
    <div
      aria-hidden
      className="relative hidden size-40 shrink-0 place-items-center sm:grid md:size-48"
    >
      {rings.map((inset, i) => (
        <motion.span
          key={inset}
          className={cn("absolute rounded-full border border-brand/30", inset)}
          animate={{ scale: [1, 1.08, 1], opacity: [0.6, 0.2, 0.6] }}
          transition={{
            duration: 3 + i,
            repeat: Infinity,
            ease: "easeInOut",
            delay: i * 0.4,
          }}
        />
      ))}
      <motion.div
        className="absolute inset-[30%] rounded-full bg-brand-gradient shadow-glow"
        animate={{ scale: [1, 1.08, 1] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
      />
      <span className="relative grid place-items-center text-brand-foreground">
        <Sparkles className="size-6" />
      </span>
      <motion.div
        className="absolute inset-0"
        animate={{ rotate: 360 }}
        transition={{ duration: 9, repeat: Infinity, ease: "linear" }}
      >
        <span className="absolute left-1/2 top-1 size-2.5 -translate-x-1/2 rounded-full bg-brand shadow-glow" />
      </motion.div>
    </div>
  );
}

export function DashboardHero() {
  const t = useTranslations("dashboard.owner.hero");

  return (
    <motion.div
      variants={scaleIn}
      initial="hidden"
      animate="visible"
      className="relative overflow-hidden rounded-md border border-border bg-card p-6 shadow-soft sm:p-8"
    >
      <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-brand/15 blur-3xl" />
      <div className="relative flex flex-col items-start justify-between gap-8 md:flex-row md:items-center">
        <div className="max-w-xl">
          <Badge>
            <span className="size-1.5 animate-pulse-glow rounded-full bg-brand" />
            {t("badge")}
          </Badge>
          <h2 className="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl md:text-4xl">
            {t("title")}
          </h2>
          <p className="mt-2 text-pretty text-muted-foreground">{t("subtitle")}</p>
        </div>
        <HeroIllustration />
      </div>
    </motion.div>
  );
}
