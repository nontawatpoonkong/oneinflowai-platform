import dynamic from "next/dynamic";

import { Hero } from "@/components/landing/hero";
import { LandingMotion } from "@/components/landing/landing-motion";
import { ProductStory } from "@/components/landing/product-story";
import { SiteShell } from "@/components/layout/site-shell";
import { DemoChat } from "@/components/demo/demo-chat";

// Below-the-fold sections are code-split (SSR kept for SEO).
const PricingPreview = dynamic(() =>
  import("@/components/landing/pricing-preview").then((m) => m.PricingPreview),
);
const Faq = dynamic(() => import("@/components/landing/faq").then((m) => m.Faq));
const Cta = dynamic(() => import("@/components/landing/cta").then((m) => m.Cta));

export default function LandingPage() {
  return (
    <>
      <LandingMotion>
        <SiteShell>
          <Hero />
          <ProductStory />
          <PricingPreview />
          <Faq />
          <Cta />
        </SiteShell>
      </LandingMotion>
      <DemoChat />
    </>
  );
}
