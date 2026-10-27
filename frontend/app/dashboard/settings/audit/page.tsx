import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AuditLogView } from "@/components/dashboard/settings/audit-log-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("auditLog");
  return { title: t("title") };
}

export default function AuditLogPage() {
  return <AuditLogView />;
}
