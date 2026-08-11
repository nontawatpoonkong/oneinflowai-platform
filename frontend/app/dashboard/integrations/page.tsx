import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { ChannelSettings } from "@/components/dashboard/integrations/channel-settings";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("integrations") };
}

export default async function IntegrationsPage() {
  return <ChannelSettings />;
}
