"use client";

import { useTranslations } from "next-intl";

import { SectionHeading } from "@/components/shared/section-heading";
import { FlowDiagram } from "@/components/shared/flow-diagram";
import { HOTEL_FLOW } from "@/lib/mock-data";

export function HotelIntegration() {
  const t = useTranslations("landing.hotel");
  const nodes = HOTEL_FLOW.map((node) => ({
    ...node,
    label: t(`nodes.${node.id}`),
  }));

  return (
    <section className="border-y border-border bg-muted/30 py-24">
      <div className="container-wide grid items-center gap-12 lg:grid-cols-2">
        <FlowDiagram nodes={nodes} className="order-2 lg:order-1" />
        <SectionHeading
          align="left"
          eyebrow={t("eyebrow")}
          title={t("title")}
          description={t("description")}
          className="order-1 lg:order-2"
        />
      </div>
    </section>
  );
}
