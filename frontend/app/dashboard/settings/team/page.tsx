import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { TeamAccessView } from "@/components/dashboard/settings/team-access-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("teamAccess");
  return { title: t("title") };
}

export default function TeamAccessPage() {
  return <TeamAccessView />;
}
