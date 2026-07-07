import type { Metadata } from "next";
import { Users } from "lucide-react";
import { getTranslations } from "next-intl/server";

import { PagePlaceholder } from "@/components/dashboard/page-placeholder";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("customers") };
}

export default async function CustomersPage() {
  const tNav = await getTranslations("dashboard.nav");
  const tp = await getTranslations("dashboard.placeholders");
  const title = tNav("customers");
  return (
    <PagePlaceholder
      title={title}
      comingSoonTitle={tp("comingSoonTitle", { title })}
      description={tp("customers")}
      icon={Users}
    />
  );
}
