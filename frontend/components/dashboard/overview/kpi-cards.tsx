"use client";

import { motion } from "framer-motion";
import {
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  MessageSquare,
  Timer,
  UserPlus,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";

import { CountUp } from "@/components/shared/count-up";
import { Card } from "@/components/ui/card";
import { fadeUp, staggerContainer, VIEWPORT } from "@/lib/animations";
import { cn } from "@/lib/utils";

interface Kpi {
  id: string;
  icon: LucideIcon;
  value: number;
  suffix?: string;
  unitKey?: "seconds";
  delta: number;
  trend: "up" | "down";
  positive: boolean;
}

// Mock values (layout-only redesign; no API).
const KPIS: Kpi[] = [
  { id: "conversations", icon: MessageSquare, value: 125, delta: 18, trend: "up", positive: true },
  { id: "replyRate", icon: Bot, value: 82, suffix: "%", delta: 6, trend: "up", positive: true },
  { id: "newCustomers", icon: UserPlus, value: 42, delta: 8, trend: "up", positive: true },
  { id: "avgResponse", icon: Timer, value: 18, unitKey: "seconds", delta: 32, trend: "down", positive: true },
];

type KpiId = "conversations" | "replyRate" | "newCustomers" | "avgResponse";

interface KpiCardsProps {
  /** Real values from the API; falls back to mock when omitted. Layout unchanged. */
  values?: Record<KpiId, number>;
}

export function KpiCards({ values }: KpiCardsProps) {
  const t = useTranslations("dashboard.owner.kpi");
  const tUnits = useTranslations("units");

  return (
    <motion.div
      variants={staggerContainer}
      initial="hidden"
      whileInView="visible"
      viewport={VIEWPORT}
      className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
    >
      {KPIS.map((kpi) => {
        const suffix = kpi.suffix ?? (kpi.unitKey ? ` ${tUnits(kpi.unitKey)}` : "");
        const Arrow = kpi.trend === "up" ? ArrowUpRight : ArrowDownRight;
        const sign = kpi.trend === "up" ? "+" : "-";
        return (
          <motion.div key={kpi.id} variants={fadeUp}>
            <Card className="p-5">
              <div className="flex items-center justify-between">
                <span className="grid size-10 place-items-center rounded-xl bg-brand/10 text-brand">
                  <kpi.icon className="size-5" />
                </span>
                <span
                  className={cn(
                    "inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-medium",
                    kpi.positive
                      ? "bg-positive/10 text-positive"
                      : "bg-destructive/10 text-destructive",
                  )}
                >
                  <Arrow className="size-3" />
                  {sign}
                  {kpi.delta}%
                </span>
              </div>
              <div className="mt-4 text-3xl font-semibold tracking-tight">
                <CountUp
                  value={values?.[kpi.id as KpiId] ?? kpi.value}
                  suffix={suffix}
                />
              </div>
              <p className="mt-1 text-sm text-muted-foreground">{t(kpi.id)}</p>
              <p className="mt-0.5 text-xs text-muted-foreground/70">
                {t("vsYesterday")}
              </p>
            </Card>
          </motion.div>
        );
      })}
    </motion.div>
  );
}
