"use client";

import { motion } from "framer-motion";
import { Moon } from "lucide-react";
import { useTranslations } from "next-intl";

import { CountUp } from "@/components/shared/count-up";
import { MetricTile } from "@/components/shared/metric-tile";
import { Badge } from "@/components/ui/badge";
import { fadeUp, staggerContainer, VIEWPORT } from "@/lib/animations";
import { COST_METRICS } from "@/lib/premium-data";
import { formatCurrencyTHB } from "@/utils/format";

export function CostSaving() {
  const t = useTranslations("landing.costSaving");
  const tUnits = useTranslations("units");

  return (
    <section className="container-wide py-24">
      <motion.div
        variants={fadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={VIEWPORT}
        className="mx-auto flex max-w-2xl flex-col items-center gap-4 text-center"
      >
        <Badge>
          <Moon className="size-3" /> {t("badge")}
        </Badge>
        <h2 className="text-balance text-3xl font-semibold tracking-tight sm:text-5xl">
          {t("title")}
        </h2>
        <p className="text-muted-foreground">{t("description")}</p>
      </motion.div>

      <motion.div
        variants={staggerContainer}
        initial="hidden"
        whileInView="visible"
        viewport={VIEWPORT}
        className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3"
      >
        {COST_METRICS.map((metric) => {
          const suffix = metric.suffix
            ? metric.suffix
            : metric.unit
              ? ` ${tUnits(metric.unit)}`
              : "";
          return (
            <MetricTile key={metric.id} icon={metric.icon} label={t(`items.${metric.id}`)}>
              <CountUp
                value={metric.value}
                decimals={metric.decimals}
                suffix={suffix}
                format={metric.currency ? formatCurrencyTHB : undefined}
              />
            </MetricTile>
          );
        })}
      </motion.div>
    </section>
  );
}
