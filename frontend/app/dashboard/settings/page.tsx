import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { SettingsView } from "@/components/dashboard/settings/settings-view";

export async function generateMetadata(): Promise<Metadata> { const t=await getTranslations("meta"); return {title:t("settings")}; }
export default function SettingsPage(){return <SettingsView/>;}
