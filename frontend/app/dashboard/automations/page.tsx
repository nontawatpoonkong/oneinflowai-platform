import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AutomationsView } from "@/components/dashboard/automations/automations-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("automations") };
}

export default function AutomationsPage() {
  return <AutomationsView />;
}
