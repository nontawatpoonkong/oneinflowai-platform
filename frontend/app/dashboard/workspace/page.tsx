import type { Metadata } from "next";
import { Boxes } from "lucide-react";
import { getTranslations } from "next-intl/server";

import { PagePlaceholder } from "@/components/dashboard/page-placeholder";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("workspace") };
}

export default async function WorkspacePage() {
  const tNav = await getTranslations("dashboard.nav");
  const tp = await getTranslations("dashboard.placeholders");
  const title = tNav("workspace");
  return (
    <PagePlaceholder
      title={title}
      comingSoonTitle={tp("comingSoonTitle", { title })}
      description={tp("workspace")}
      icon={Boxes}
    />
  );
}
