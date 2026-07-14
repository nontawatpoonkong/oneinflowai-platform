"use client";

import { motion } from "framer-motion";
import { Bot, Clock, Lightbulb, PiggyBank, Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";

import { Card } from "@/components/ui/card";
import { fadeUp, VIEWPORT } from "@/lib/animations";
import type { DashboardOverview } from "@/services/dashboard/dashboard.service";
import { formatCurrencyTHB, formatNumber } from "@/utils/format";

const DASH = "—";

/** Business Insight card. Reads dashboard data; missing fields render as "—". */
export function InsightCard({ data }: { data?: DashboardOverview }) {
  const t = useTranslations("dashboard.owner.insight");

  const replyRate = data?.ai_reply_rate;
  const hours = data?.saving_hours;
  const cost = data?.saving_cost;
  const peakHour = data?.peak_hour;
  const recommendation = data?.recommendation;

  const stats = [
    {
      id: "replyRate",
      icon: Bot,
      label: t("aiReplyRate"),
      value: replyRate == null ? DASH : `${formatNumber(replyRate)}%`,
    },
    {
      id: "savingHours",
      icon: Clock,
      label: t("savingHours"),
      value: hours == null ? DASH : `${formatNumber(hours)} ${t("hoursUnit")}`,
    },
    {
      id: "savingCost",
      icon: PiggyBank,
      label: t("savingCost"),
      value: cost == null ? DASH : formatCurrencyTHB(cost),
    },
    {
      id: "peakHour",
      icon: Clock,
      label: t("peakHour"),
      value: peakHour == null || peakHour === "" ? DASH : String(peakHour),
    },
  ];

  return (
    <motion.div
      variants={fadeUp}
      initial="hidden"
      whileInView="visible"
      viewport={VIEWPORT}
    >
      <Card className="p-6">
        <div className="flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl bg-brand/10 text-brand">
            <Sparkles className="size-5" />
          </span>
          <div>
            <h2 className="font-semibold tracking-tight">{t("title")}</h2>
            <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
          </div>
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {stats.map((stat) => (
            <div
              key={stat.id}
              className="flex flex-col gap-1 rounded-2xl border border-border bg-muted/20 p-4"
            >
              <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                <stat.icon className="size-3.5" />
                {stat.label}
              </span>
              <span className="text-lg font-semibold tabular-nums">{stat.value}</span>
            </div>
          ))}
        </div>

        <div className="mt-4 flex items-start gap-3 rounded-2xl border border-brand/30 bg-brand/5 p-4">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-brand/10 text-brand">
            <Lightbulb className="size-4" />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-medium text-muted-foreground">
              {t("recommendation")}
            </p>
            <p className="mt-0.5 text-sm">
              {recommendation == null || recommendation === "" ? DASH : recommendation}
            </p>
          </div>
        </div>
      </Card>
    </motion.div>
  );
}
