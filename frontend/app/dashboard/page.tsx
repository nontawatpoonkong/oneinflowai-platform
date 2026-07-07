import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { DashboardOverview } from "@/components/dashboard/overview/dashboard-overview";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("dashboard") };
}

export default function DashboardPage() {
  return <DashboardOverview />;
}
