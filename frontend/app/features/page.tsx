import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { Cta } from "@/components/landing/cta";
import { Features } from "@/components/landing/features";
import { HowItWorks } from "@/components/landing/how-it-works";
import { SiteShell } from "@/components/layout/site-shell";
import { SectionHeading } from "@/components/shared/section-heading";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("features") };
}

export default async function FeaturesPage() {
  const t = await getTranslations("landing.features");
  return (
    <SiteShell>
      <div className="container-wide pt-20 pb-8">
        <SectionHeading
          eyebrow={t("eyebrow")}
          title={t("title")}
          description={t("description")}
        />
      </div>
      <Features />
      <HowItWorks />
      <Cta />
    </SiteShell>
  );
}
