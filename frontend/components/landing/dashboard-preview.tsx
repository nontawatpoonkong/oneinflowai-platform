"use client";

import { motion } from "framer-motion";
import { useTranslations } from "next-intl";

import { DashboardMock } from "@/components/dashboard/dashboard-mock";
import { DashboardSidebar } from "@/components/dashboard/sidebar";
import { SectionHeading } from "@/components/shared/section-heading";
import { scaleIn, VIEWPORT } from "@/lib/animations";

export function DashboardPreview() {
  const t = useTranslations("landing.dashboardPreview");

  return (
    <section id="dashboard" className="container-wide py-24">
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("title")}
        description={t("description")}
      />

      <motion.div
        variants={scaleIn}
        initial="hidden"
        whileInView="visible"
        viewport={VIEWPORT}
        className="mt-12 overflow-hidden rounded-3xl border border-border bg-card shadow-soft"
      >
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <span className="size-3 rounded-full bg-destructive/70" />
          <span className="size-3 rounded-full bg-warning/80" />
          <span className="size-3 rounded-full bg-positive/80" />
          <span className="ml-3 text-xs text-muted-foreground">
            app.oneflow.ai/dashboard
          </span>
        </div>

        <div className="flex">
          <div className="hidden md:block">
            <DashboardSidebar />
          </div>
          <div className="min-w-0 flex-1 p-4 sm:p-6">
            <DashboardMock />
          </div>
        </div>
      </motion.div>
    </section>
  );
}
