"use client";

import { motion } from "framer-motion";
import { useTranslations } from "next-intl";

import { CountUp } from "@/components/shared/count-up";
import { MetricTile } from "@/components/shared/metric-tile";
import { SectionHeading } from "@/components/shared/section-heading";
import { useLiveMetrics } from "@/hooks/use-live-metrics";
import { staggerContainer, VIEWPORT } from "@/lib/animations";
import { LIVE_METRICS } from "@/lib/premium-data";
import { formatCurrencyTHB } from "@/utils/format";

export function LiveMetrics() {
  const t = useTranslations("landing.liveMetrics");
  const tUnits = useTranslations("units");
  const values = useLiveMetrics(LIVE_METRICS);

  return (
    <section className="container-wide py-24">
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("title")}
        description={t("description")}
      />

      <motion.div
        variants={staggerContainer}
        initial="hidden"
        whileInView="visible"
        viewport={VIEWPORT}
        className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3"
      >
        {LIVE_METRICS.map((metric) => {
          const suffix = metric.suffix
            ? metric.suffix
            : metric.unit
              ? ` ${tUnits(metric.unit)}`
              : "";
          return (
            <MetricTile
              key={metric.id}
              icon={metric.icon}
              label={t(`items.${metric.id}`)}
              hint={metric.live ? t("eyebrow") : undefined}
            >
              <CountUp
                value={values[metric.id]}
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
