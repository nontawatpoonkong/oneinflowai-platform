"use client";

import { motion } from "framer-motion";
import { useTranslations } from "next-intl";

import { GlowCard } from "@/components/shared/glow-card";
import { SectionHeading } from "@/components/shared/section-heading";
import { fadeUp, staggerContainer, VIEWPORT } from "@/lib/animations";
import { FEATURES } from "@/lib/mock-data";

export function Features() {
  const t = useTranslations("landing.features");

  return (
    <section id="features" className="container-wide py-24">
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
        {FEATURES.map((feature) => (
          <GlowCard key={feature.id} variants={fadeUp}>
            <motion.span
              whileHover={{ rotate: -8, scale: 1.08 }}
              transition={{ type: "spring", stiffness: 300, damping: 12 }}
              className="mb-5 grid size-12 place-items-center rounded-2xl bg-brand/10 text-brand"
            >
              <feature.icon className="size-6" />
            </motion.span>
            <h3 className="text-lg font-semibold tracking-tight">
              {t(`items.${feature.id}.title`)}
            </h3>
            <p className="mt-2 text-sm text-muted-foreground">
              {t(`items.${feature.id}.description`)}
            </p>
          </GlowCard>
        ))}
      </motion.div>
    </section>
  );
}
