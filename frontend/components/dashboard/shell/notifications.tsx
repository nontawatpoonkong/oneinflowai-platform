"use client";

import { Bell } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

import { useDropdown } from "@/components/dashboard/shell/use-dropdown";
import { EmptyState } from "@/components/shared/empty-state";
import { useNotificationActions, useNotifications } from "@/hooks/api/use-notifications";
import { cn } from "@/lib/utils";

export function Notifications() {
  const t = useTranslations("dashboard.shell");
  const { open, setOpen, ref } = useDropdown();
  const router = useRouter();
  const notifications = useNotifications();
  const actions = useNotificationActions();

  function openNotification(item: NonNullable<typeof notifications.data>["items"][number]) {
    if (!item.is_read) actions.markRead.mutate(item.id);
    if (item.entity_type === "CONVERSATION") {
      router.push(`/dashboard/inbox?conversation=${encodeURIComponent(item.entity_id)}`);
    } else {
      router.push("/dashboard");
    }
    setOpen(false);
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={t("notifications")}
        aria-expanded={open}
        className="relative grid size-9 place-items-center rounded-full border border-border text-muted-foreground transition-colors hover:text-foreground"
      >
        <Bell className="size-4" />
        {(notifications.data?.unread_count ?? 0) > 0 ? (
          <span className="absolute right-0 top-0 grid min-w-4 place-items-center rounded-full bg-destructive px-1 text-[9px] font-semibold text-destructive-foreground">
            {notifications.data?.unread_count}
          </span>
        ) : null}
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
        <div className="flex items-center justify-between px-2 py-2">
          <p className="text-sm font-medium">{t("notifications")}</p>
          {(notifications.data?.unread_count ?? 0) > 0 ? (
            <button type="button" onClick={() => actions.markAllRead.mutate()} className="text-xs text-brand hover:underline">
              {t("markAllRead")}
            </button>
          ) : null}
        </div>
        {notifications.data?.items.length ? (
          <ul className="max-h-96 overflow-y-auto">
            {notifications.data.items.map((item) => (
              <li key={item.id}>
                <button type="button" onClick={() => openNotification(item)} className={cn("w-full rounded-xl px-3 py-2 text-left hover:bg-accent", !item.is_read && "bg-brand/5")}>
                  <p className="text-sm font-medium">{item.title}</p>
                  <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{item.body}</p>
                  <time className="mt-1 block text-[10px] text-muted-foreground">{new Date(item.created_at).toLocaleString()}</time>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState icon={Bell} title={t("notificationsEmptyTitle")} description={t("notificationsEmptyDesc")} className="border-0 bg-transparent py-8" />
        )}
      </div>
    </div>
  );
}
