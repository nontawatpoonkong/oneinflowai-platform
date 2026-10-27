"use client";

import { ArrowRight, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { SectionHeading } from "@/components/shared/section-heading";
import { Button } from "@/components/ui/button";

export function PricingPreview() {
  const t = useTranslations("landing.pricing");
  const included = t.raw("included") as string[];

  return (
    <section id="pricing" className="container-wide py-20 sm:py-24">
      <SectionHeading eyebrow={t("eyebrow")} title={t("title")} description={t("description")} />
      <div className="mx-auto mt-10 grid max-w-4xl overflow-hidden rounded-xl border border-border bg-card lg:grid-cols-[1.1fr_0.9fr]">
        <div className="p-6 sm:p-8">
          <h3 className="text-xl font-semibold tracking-tight">{t("contactTitle")}</h3>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{t("contactDescription")}</p>
          <div className="mt-6 flex flex-wrap gap-2">
            <Button asChild><Link href="/register">{t("primaryCta")}<ArrowRight /></Link></Button>
            <Button asChild variant="outline"><Link href="/docs">{t("secondaryCta")}</Link></Button>
          </div>
        </div>
        <div className="border-t border-border bg-surface p-6 sm:p-8 lg:border-l lg:border-t-0">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">{t("includedTitle")}</p>
          <ul className="mt-4 space-y-3">
            {included.map((item) => <li key={item} className="flex items-start gap-2 text-sm"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-positive" /><span>{item}</span></li>)}
          </ul>
        </div>
      </div>
    </section>
  );
}
