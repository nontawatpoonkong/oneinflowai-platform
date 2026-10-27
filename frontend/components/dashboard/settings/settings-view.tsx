"use client";

import { Bot, Boxes, BrainCircuit, Building2, CreditCard, Plug, Settings2, Users } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { PageHeader } from "@/components/dashboard/shared/page-header";

const sections = [
  { key: "workspace", href: "/dashboard/workspace", icon: Boxes },
  { key: "hotel", href: "/dashboard/hotel/rooms", icon: Building2 },
  { key: "team", href: "/dashboard/settings/team", icon: Users },
  { key: "ai", href: "/dashboard/knowledge", icon: BrainCircuit },
  { key: "channels", href: "/dashboard/integrations", icon: Plug },
  { key: "automations", href: "/dashboard/automations", icon: Bot },
  { key: "integrations", href: "/dashboard/hotel/pms", icon: Settings2 },
  { key: "billing", href: "/dashboard/billing", icon: CreditCard },
] as const;

export function SettingsView() {
  const t = useTranslations("settingsHub");
  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("description")} />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {sections.map(({ key, href, icon: Icon }) => (
          <Link key={key} href={href} className="group flex items-start gap-3 rounded-lg border border-border bg-card p-4 transition-colors hover:border-brand/40 hover:bg-muted/30">
            <span className="grid size-9 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground group-hover:bg-brand-soft group-hover:text-brand"><Icon className="size-[18px]" /></span>
            <span><span className="block text-sm font-semibold">{t(`sections.${key}.title`)}</span><span className="mt-1 block text-sm leading-5 text-muted-foreground">{t(`sections.${key}.description`)}</span></span>
          </Link>
        ))}
      </div>
    </div>
  );
}
