import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { GuestDetail } from "@/components/dashboard/customers/guest-detail";

export async function generateMetadata():Promise<Metadata>{const t=await getTranslations("guestCrm");return {title:t("detailTitle")};}
export default async function GuestDetailPage({params}:{params:Promise<{customerId:string}>}){const {customerId}=await params;return <GuestDetail customerId={customerId}/>;}
