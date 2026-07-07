"use client";

import { Bell } from "lucide-react";
import { useTranslations } from "next-intl";

import { useDropdown } from "@/components/dashboard/shell/use-dropdown";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";

export function Notifications() {
  const t = useTranslations("dashboard.shell");
  const { open, setOpen, ref } = useDropdown();

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={t("notifications")}
        aria-expanded={open}
        className="grid size-9 place-items-center rounded-full border border-border text-muted-foreground transition-colors hover:text-foreground"
      >
        <Bell className="size-4" />
      </button>

      <div
        role="menu"
        className={cn(
          "absolute right-0 mt-2 w-80 origin-top-right rounded-2xl border border-border bg-popover p-2 shadow-soft transition-all",
          open
            ? "pointer-events-auto scale-100 opacity-100"
            : "pointer-events-none scale-95 opacity-0",
        )}
      >
        <p className="px-2 py-2 text-sm font-medium">{t("notifications")}</p>
        <EmptyState
          icon={Bell}
          title={t("notificationsEmptyTitle")}
          description={t("notificationsEmptyDesc")}
          className="border-0 bg-transparent py-8"
        />
      </div>
    </div>
  );
}
