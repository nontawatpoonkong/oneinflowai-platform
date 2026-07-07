"use client";

import { Check } from "lucide-react";
import { motion } from "framer-motion";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { SectionHeading } from "@/components/shared/section-heading";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fadeUp, staggerContainer, VIEWPORT } from "@/lib/animations";
import { cn } from "@/lib/utils";
import { formatCurrencyTHB } from "@/utils/format";
import { PRICING_PLANS } from "@/lib/mock-data";

export function PricingPreview() {
  const t = useTranslations("landing.pricing");

  return (
    <section id="pricing" className="container-wide py-24">
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
        className="mt-12 grid items-stretch gap-6 lg:grid-cols-3"
      >
        {PRICING_PLANS.map((plan) => {
          const features = t.raw(`plans.${plan.id}.features`) as string[];
          return (
            <motion.div
              key={plan.id}
              variants={fadeUp}
              className={cn(
                "relative flex flex-col gap-6 rounded-3xl border p-8 shadow-soft",
                plan.highlighted
                  ? "border-brand/50 bg-card ring-1 ring-brand/30 lg:-translate-y-3"
                  : "border-border bg-card",
              )}
            >
              {plan.highlighted ? (
                <Badge className="absolute -top-3 left-1/2 -translate-x-1/2">
                  {t("popular")}
                </Badge>
              ) : null}

              <div className="flex flex-col gap-2">
                <h3 className="text-lg font-semibold">{t(`plans.${plan.id}.name`)}</h3>
                <p className="text-sm text-muted-foreground">
                  {t(`plans.${plan.id}.description`)}
                </p>
              </div>

              <div className="flex items-baseline gap-1">
                <span className="text-4xl font-semibold tracking-tight">
                  {plan.price === 0 ? t("free") : formatCurrencyTHB(plan.price)}
                </span>
                {plan.price > 0 ? (
                  <span className="text-sm text-muted-foreground">
                    /{t(`periods.${plan.period}`)}
                  </span>
                ) : null}
              </div>

              <ul className="flex flex-col gap-3">
                {features.map((feature) => (
                  <li key={feature} className="flex items-center gap-2 text-sm">
                    <Check className="size-4 shrink-0 text-brand" />
                    {feature}
                  </li>
                ))}
              </ul>

              <Button
                asChild
                variant={plan.highlighted ? "default" : "outline"}
                className="mt-auto w-full"
              >
                <Link href="/login">{t(`plans.${plan.id}.cta`)}</Link>
              </Button>
            </motion.div>
          );
        })}
      </motion.div>
    </section>
  );
}
