"use client";

import { useTranslations } from "next-intl";

import { AIPipeline } from "@/components/shared/ai-pipeline";
import { SectionHeading } from "@/components/shared/section-heading";

export function AIFlow() {
  const t = useTranslations("landing.aiFlow");

  return (
    <section className="container-wide py-24">
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("title")}
        description={t("description")}
      />
      <div className="mt-14">
        <AIPipeline />
      </div>
    </section>
  );
}
