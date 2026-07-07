"use client";

import { motion } from "framer-motion";
import { useTranslations } from "next-intl";

import { SectionHeading } from "@/components/shared/section-heading";
import { fadeUp, staggerContainer, VIEWPORT } from "@/lib/animations";
import { HOW_IT_WORKS } from "@/lib/mock-data";

export function HowItWorks() {
  const t = useTranslations("landing.howItWorks");

  return (
    <section className="border-y border-border bg-muted/30 py-24">
      <div className="container-wide">
        <SectionHeading
          eyebrow={t("eyebrow")}
          title={t("title")}
          description={t("description")}
        />

        <motion.ol
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={VIEWPORT}
          className="mt-14 grid gap-6 md:grid-cols-2 lg:grid-cols-4"
        >
          {HOW_IT_WORKS.map((step, index) => (
            <motion.li
              key={step.id}
              variants={fadeUp}
              className="relative flex flex-col gap-4 rounded-2xl border border-border bg-card p-6 shadow-soft"
            >
              <span className="absolute -top-3 left-6 rounded-full bg-brand px-3 py-0.5 text-xs font-semibold text-brand-foreground">
                {t("step")} {index + 1}
              </span>
              <span className="grid size-11 place-items-center rounded-2xl bg-brand/10 text-brand">
                <step.icon className="size-5" />
              </span>
              <div>
                <h3 className="font-semibold tracking-tight">
                  {t(`items.${step.id}.title`)}
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {t(`items.${step.id}.description`)}
                </p>
              </div>
            </motion.li>
          ))}
        </motion.ol>
      </div>
    </section>
  );
}
