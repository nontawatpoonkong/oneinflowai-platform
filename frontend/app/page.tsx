import dynamic from "next/dynamic";

import { Features } from "@/components/landing/features";
import { Hero } from "@/components/landing/hero";
import { HowItWorks } from "@/components/landing/how-it-works";
import { LiveMetrics } from "@/components/landing/live-metrics";
import { SiteShell } from "@/components/layout/site-shell";
import { GlowCursor } from "@/components/shared/glow-cursor";
import { DemoChat } from "@/components/demo/demo-chat";

// Below-the-fold sections are code-split (SSR kept for SEO).
const DashboardPreview = dynamic(() =>
  import("@/components/landing/dashboard-preview").then((m) => m.DashboardPreview),
);
const RoiCalculator = dynamic(() =>
  import("@/components/landing/roi-calculator").then((m) => m.RoiCalculator),
);
const AIFlow = dynamic(() =>
  import("@/components/landing/ai-flow").then((m) => m.AIFlow),
);
const HotelIntegration = dynamic(() =>
  import("@/components/landing/hotel-integration").then((m) => m.HotelIntegration),
);
const CostSaving = dynamic(() =>
  import("@/components/landing/cost-saving").then((m) => m.CostSaving),
);
const Trust = dynamic(() =>
  import("@/components/landing/trust").then((m) => m.Trust),
);
const PricingPreview = dynamic(() =>
  import("@/components/landing/pricing-preview").then((m) => m.PricingPreview),
);
const Faq = dynamic(() => import("@/components/landing/faq").then((m) => m.Faq));
const Cta = dynamic(() => import("@/components/landing/cta").then((m) => m.Cta));

export default function LandingPage() {
  return (
    <>
      <GlowCursor />
      <SiteShell>
        <Hero />
        <LiveMetrics />
        <Features />
        <HowItWorks />
        <DashboardPreview />
        <RoiCalculator />
        <AIFlow />
        <HotelIntegration />
        <CostSaving />
        <Trust />
        <PricingPreview />
        <Faq />
        <Cta />
      </SiteShell>
      <DemoChat />
    </>
  );
}
