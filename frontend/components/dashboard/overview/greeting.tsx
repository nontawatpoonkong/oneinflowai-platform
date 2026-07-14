"use client";

import { motion } from "framer-motion";
import { useTranslations } from "next-intl";

import { useAuth } from "@/hooks/use-auth";
import { useMounted } from "@/hooks/use-mounted";
import { fadeUp } from "@/lib/animations";

function periodKey(hour: number): "morning" | "afternoon" | "evening" {
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
}

export function Greeting() {
  const t = useTranslations("dashboard.owner");
  const { user } = useAuth();
  const mounted = useMounted();

  const name =
    user?.full_name?.trim().split(/\s+/)[0] || t("greeting.fallbackName");
  // Deterministic first render (matches SSR); refine to local time after mount.
  const key = mounted ? periodKey(new Date().getHours()) : "afternoon";

  return (
    <motion.div variants={fadeUp} initial="hidden" animate="visible">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
        {t(`greeting.${key}`, { name })}
      </h1>
      <p className="mt-1 text-muted-foreground">{t("welcomeBack")}</p>
    </motion.div>
  );
}
