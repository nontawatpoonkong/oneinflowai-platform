import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { GuestList } from "@/components/dashboard/customers/guest-list";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("customers") };
}

export default async function CustomersPage() {
  return <GuestList />;
}
