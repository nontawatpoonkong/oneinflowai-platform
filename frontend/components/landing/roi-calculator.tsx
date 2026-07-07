"use client";

import { motion } from "framer-motion";
import { TrendingUp } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { SectionHeading } from "@/components/shared/section-heading";
import { Card } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { fadeUp, VIEWPORT } from "@/lib/animations";
import { ROI } from "@/lib/premium-data";
import type { RoiInput } from "@/types";
import { formatCurrencyTHB, formatNumber } from "@/utils/format";

interface Result {
  yearlySavings: number;
  automationPct: number;
  responseImprovement: number;
  roiPct: number;
}

function calculate({ employees, salary, dailyConversations }: RoiInput): Result {
  const yearlyLabor = employees * salary * 12;
  const yearlySavings = Math.round(yearlyLabor * ROI.automationRate);
  const humanSeconds = ROI.humanReplyMinutes * 60;
  const responseImprovement = Math.round(humanSeconds / ROI.aiReplySeconds);
  const roiPct = Math.round(
    ((yearlySavings - ROI.platformYearlyCost) / ROI.platformYearlyCost) * 100,
  );
  const automationPct = Math.min(
    ROI.automationRate * 100,
    90 + Math.min(dailyConversations / 400, 9),
  );
  return { yearlySavings, automationPct, responseImprovement, roiPct };
}

export function RoiCalculator() {
  const t = useTranslations("landing.roi");
  const [input, setInput] = useState<RoiInput>({
    employees: ROI.defaults.employees,
    salary: ROI.defaults.salary,
    dailyConversations: ROI.defaults.dailyConversations,
  });

  const result = useMemo(() => calculate(input), [input]);

  const cards = [
    { label: t("results.savings"), value: formatCurrencyTHB(result.yearlySavings), accent: true },
    { label: t("results.automation"), value: `${result.automationPct.toFixed(1)}%` },
    { label: t("results.faster"), value: `${formatNumber(result.responseImprovement)}×` },
    { label: t("results.roi"), value: `${formatNumber(result.roiPct)}%` },
  ];

  return (
    <section id="roi" className="border-y border-border bg-muted/30 py-24">
      <div className="container-wide">
        <SectionHeading
          eyebrow={t("eyebrow")}
          title={t("title")}
          description={t("description")}
        />

        <motion.div
          variants={fadeUp}
          initial="hidden"
          whileInView="visible"
          viewport={VIEWPORT}
          className="mx-auto mt-12 grid max-w-5xl gap-6 lg:grid-cols-[1fr_1.1fr]"
        >
          <Card className="flex flex-col gap-8 p-8">
            <Slider
              label={t("sliders.employees")}
              value={input.employees}
              min={ROI.ranges.employees.min}
              max={ROI.ranges.employees.max}
              step={ROI.ranges.employees.step}
              onChange={(employees) => setInput((p) => ({ ...p, employees }))}
              format={(v) => `${v}`}
            />
            <Slider
              label={t("sliders.salary")}
              value={input.salary}
              min={ROI.ranges.salary.min}
              max={ROI.ranges.salary.max}
              step={ROI.ranges.salary.step}
              onChange={(salary) => setInput((p) => ({ ...p, salary }))}
              format={formatCurrencyTHB}
            />
            <Slider
              label={t("sliders.conversations")}
              value={input.dailyConversations}
              min={ROI.ranges.dailyConversations.min}
              max={ROI.ranges.dailyConversations.max}
              step={ROI.ranges.dailyConversations.step}
              onChange={(dailyConversations) =>
                setInput((p) => ({ ...p, dailyConversations }))
              }
              format={formatNumber}
            />
          </Card>

          <div className="grid gap-4 sm:grid-cols-2">
            {cards.map((card) => (
              <Card
                key={card.label}
                className={
                  card.accent
                    ? "flex flex-col justify-center gap-2 border-brand/40 p-6 ring-1 ring-brand/20 sm:col-span-2"
                    : "flex flex-col justify-center gap-2 p-6"
                }
              >
                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                  <TrendingUp className="size-3.5 text-brand" />
                  {card.label}
                </span>
                <motion.span
                  key={card.value}
                  initial={{ opacity: 0.4, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25 }}
                  className={
                    card.accent
                      ? "text-4xl font-semibold tracking-tight text-gradient"
                      : "text-2xl font-semibold tracking-tight"
                  }
                >
                  {card.value}
                </motion.span>
              </Card>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
