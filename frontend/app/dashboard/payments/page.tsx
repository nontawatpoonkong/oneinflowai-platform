import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { PaymentsView } from "@/components/dashboard/payments/payments-view";

export async function generateMetadata(): Promise<Metadata> { const t = await getTranslations("meta"); return { title: t("payments") }; }
export default function PaymentsPage() { return <PaymentsView />; }
