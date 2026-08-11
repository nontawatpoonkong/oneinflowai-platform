import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { NotificationsView } from "@/components/dashboard/notifications/notifications-view";

export async function generateMetadata(): Promise<Metadata> { const t = await getTranslations("meta"); return { title: t("notifications") }; }
export default function NotificationsPage() { return <NotificationsView />; }
