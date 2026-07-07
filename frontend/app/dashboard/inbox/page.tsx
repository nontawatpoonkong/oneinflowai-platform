import type { Metadata } from "next";
import { Inbox } from "lucide-react";
import { getTranslations } from "next-intl/server";

import { PagePlaceholder } from "@/components/dashboard/page-placeholder";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("inbox") };
}

export default async function InboxPage() {
  const tNav = await getTranslations("dashboard.nav");
  const tp = await getTranslations("dashboard.placeholders");
  const title = tNav("inbox");
  return (
    <PagePlaceholder
      title={title}
      comingSoonTitle={tp("comingSoonTitle", { title })}
      description={tp("inbox")}
      icon={Inbox}
    />
  );
}
