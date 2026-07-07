"use client";

import { ChevronLeft } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { Logo } from "@/components/shared/logo";
import { DASHBOARD_NAV } from "@/lib/dashboard-nav";
import { cn } from "@/lib/utils";

function isActive(pathname: string, href: string): boolean {
  if (href === "/dashboard") return pathname === "/dashboard";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppSidebar({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const pathname = usePathname();
  const tNav = useTranslations("dashboard.nav");
  const tShell = useTranslations("dashboard.shell");

  return (
    <aside
      className={cn(
        "hidden shrink-0 flex-col border-r border-border bg-card/50 transition-[width] duration-300 md:flex",
        collapsed ? "w-[72px]" : "w-64",
      )}
    >
      <div
        className={cn(
          "flex h-16 items-center border-b border-border",
          collapsed ? "justify-center px-2" : "px-5",
        )}
      >
        {collapsed ? (
          <span className="grid size-9 place-items-center rounded-xl bg-brand-gradient text-brand-foreground shadow-glow">
            ●
          </span>
        ) : (
          <Logo />
        )}
      </div>

      <nav className="flex flex-1 flex-col gap-1.5 p-3">
        {DASHBOARD_NAV.map((item) => {
          const active = isActive(pathname, item.href);
          const label = tNav(item.key);
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? label : undefined}
              aria-current={active ? "page" : undefined}
              className={cn(
                "group relative flex items-center gap-3 rounded-xl px-2.5 py-2.5 text-sm transition-all",
                active
                  ? "bg-brand/10 font-semibold text-brand"
                  : "font-medium text-muted-foreground hover:bg-accent hover:text-foreground",
                collapsed && "justify-center px-0",
              )}
            >
              {active && !collapsed ? (
                <span
                  aria-hidden
                  className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-brand"
                />
              ) : null}
              <span
                className={cn(
                  "grid size-8 shrink-0 place-items-center rounded-lg transition-colors",
                  active
                    ? "bg-brand/15 text-brand"
                    : "text-muted-foreground group-hover:text-foreground",
                )}
              >
                <item.icon className="size-4" />
              </span>
              {!collapsed && <span className="truncate">{label}</span>}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border p-3">
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? tShell("expand") : tShell("collapse")}
          className={cn(
            "flex w-full items-center gap-2 rounded-xl border border-border py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
            collapsed ? "justify-center px-0" : "justify-center px-3",
          )}
        >
          <ChevronLeft
            className={cn("size-4 transition-transform", collapsed && "rotate-180")}
          />
          {!collapsed && tShell("collapse")}
        </button>
      </div>
    </aside>
  );
}
