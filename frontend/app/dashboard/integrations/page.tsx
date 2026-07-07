import type { Metadata } from "next";
import { Plug } from "lucide-react";
import { getTranslations } from "next-intl/server";

import { PagePlaceholder } from "@/components/dashboard/page-placeholder";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("integrations") };
}

export default async function IntegrationsPage() {
  const tNav = await getTranslations("dashboard.nav");
  const tp = await getTranslations("dashboard.placeholders");
  const title = tNav("integrations");
  return (
    <PagePlaceholder
      title={title}
      comingSoonTitle={tp("comingSoonTitle", { title })}
      description={tp("integrations")}
      icon={Plug}
    />
  );
}
