import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { ActionsView } from "@/components/dashboard/actions/actions-view";

export async function generateMetadata(): Promise<Metadata> { const t = await getTranslations("meta"); return { title: t("actions") }; }
export default function ActionsPage() { return <ActionsView />; }
