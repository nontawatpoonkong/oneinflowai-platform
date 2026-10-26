"use client";

import { useTranslations } from "next-intl";

import { Logo } from "@/components/shared/logo";
import { DASHBOARD_SIDEBAR } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

export function DashboardSidebar({ compact = false }: { compact?: boolean }) {
  const t = useTranslations("dashboard.nav");

  return (
    <aside
      className={cn(
        "flex flex-col gap-6 border-r border-border bg-card/60 p-4",
        compact ? "w-16 items-center" : "w-56",
      )}
    >
      <div className={cn("px-2", compact && "px-0")}>
        {compact ? (
          <span className="grid size-8 place-items-center rounded-md bg-brand-gradient text-brand-foreground">
            ●
          </span>
        ) : (
          <Logo />
        )}
      </div>

      <nav className="flex flex-1 flex-col gap-1">
        {DASHBOARD_SIDEBAR.map((item) => (
          <div
            key={item.id}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              item.active
                ? "bg-brand/10 text-brand"
                : "text-muted-foreground hover:bg-accent hover:text-foreground",
              compact && "justify-center px-0",
            )}
            title={t(item.id)}
          >
            <item.icon className="size-4 shrink-0" />
            {!compact && <span>{t(item.id)}</span>}
          </div>
        ))}
      </nav>
    </aside>
  );
}
