import type { Metadata } from "next";
import { Settings } from "lucide-react";
import { getTranslations } from "next-intl/server";

import { PagePlaceholder } from "@/components/dashboard/page-placeholder";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("settings") };
}

export default async function SettingsPage() {
  const tNav = await getTranslations("dashboard.nav");
  const tp = await getTranslations("dashboard.placeholders");
  const title = tNav("settings");
  return (
    <PagePlaceholder
      title={title}
      comingSoonTitle={tp("comingSoonTitle", { title })}
      description={tp("settings")}
      icon={Settings}
    />
  );
}
