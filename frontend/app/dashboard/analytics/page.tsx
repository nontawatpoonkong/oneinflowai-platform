import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AnalyticsView } from "@/components/dashboard/analytics/analytics-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("analytics") };
}

export default async function AnalyticsPage() {
  return <AnalyticsView />;
}
