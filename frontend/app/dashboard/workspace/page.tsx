import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { WorkspaceView } from "@/components/dashboard/workspace/workspace-view";

export async function generateMetadata(): Promise<Metadata> { const t=await getTranslations("meta"); return {title:t("workspace")}; }
export default function WorkspacePage(){return <WorkspaceView/>;}
