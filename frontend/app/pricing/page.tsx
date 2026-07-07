import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { Faq } from "@/components/landing/faq";
import { PricingPreview } from "@/components/landing/pricing-preview";
import { SiteShell } from "@/components/layout/site-shell";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("pricing") };
}

export default function PricingPage() {
  return (
    <SiteShell>
      <div className="pt-10">
        <PricingPreview />
        <Faq />
      </div>
    </SiteShell>
  );
}
