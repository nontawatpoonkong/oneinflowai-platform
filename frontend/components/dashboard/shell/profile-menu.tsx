"use client";

import { ChevronDown, LogOut, Settings, User } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { useDropdown } from "@/components/dashboard/shell/use-dropdown";
import { useAuth } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";
import { initialsFrom } from "@/utils/format";

export function ProfileMenu() {
  const t = useTranslations("dashboard.shell");
  const { user, logout } = useAuth();
  const { open, setOpen, ref } = useDropdown();
  if (!user) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-full border border-border py-1 pl-1 pr-2 transition-colors hover:bg-accent"
      >
        <span className="grid size-7 place-items-center rounded-full bg-brand text-xs font-semibold text-brand-foreground">
          {initialsFrom(user.full_name, user.email)}
        </span>
        <ChevronDown className="size-4 text-muted-foreground" />
      </button>

      <div
        role="menu"
        className={cn(
          "absolute right-0 mt-2 w-60 origin-top-right overflow-hidden rounded-2xl border border-border bg-popover p-1.5 shadow-soft transition-all",
          open
            ? "pointer-events-auto scale-100 opacity-100"
            : "pointer-events-none scale-95 opacity-0",
        )}
      >
        <div className="border-b border-border px-3 py-2.5">
          <p className="truncate text-sm font-medium">
            {user.full_name ?? t("member")}
          </p>
          <p className="truncate text-xs text-muted-foreground">{user.email}</p>
        </div>
        <Link
          href="/dashboard/settings"
          role="menuitem"
          className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm text-foreground transition-colors hover:bg-accent"
        >
          <User className="size-4 text-muted-foreground" />
          {t("profile")}
        </Link>
        <Link
          href="/dashboard/settings"
          role="menuitem"
          className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm text-foreground transition-colors hover:bg-accent"
        >
          <Settings className="size-4 text-muted-foreground" />
          {t("settings")}
        </Link>
        <button
          type="button"
          role="menuitem"
          onClick={logout}
          className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-destructive transition-colors hover:bg-destructive/10"
        >
          <LogOut className="size-4" />
          {t("logout")}
        </button>
      </div>
    </div>
  );
}
