"use client";

import { motion } from "framer-motion";
import { useTranslations } from "next-intl";

import { SectionHeading } from "@/components/shared/section-heading";
import { Badge } from "@/components/ui/badge";
import { fadeUp, staggerContainer, VIEWPORT } from "@/lib/animations";
import { INDUSTRIES } from "@/lib/premium-data";

export function Trust() {
  const t = useTranslations("landing.trust");

  return (
    <section className="border-y border-border bg-muted/30 py-24">
      <div className="container-wide">
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
          className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          {INDUSTRIES.map((industry) => (
            <motion.div
              key={industry.id}
              variants={fadeUp}
              whileHover={{ y: -4 }}
              className="group flex items-center justify-between rounded-2xl border border-border bg-card p-6 shadow-soft transition-colors hover:border-brand/40"
            >
              <div className="flex items-center gap-4">
                <span className="grid size-11 place-items-center rounded-2xl bg-brand/10 text-brand transition-transform group-hover:scale-105">
                  <industry.icon className="size-5" />
                </span>
                <span className="text-base font-semibold">
                  {t(`industries.${industry.id}`)}
                </span>
              </div>
              <Badge variant="muted">{t("comingSoon")}</Badge>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
