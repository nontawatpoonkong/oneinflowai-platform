import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { KnowledgeView } from "@/components/dashboard/knowledge/knowledge-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("knowledge") };
}

export default function KnowledgePage() {
  return <KnowledgeView />;
}
