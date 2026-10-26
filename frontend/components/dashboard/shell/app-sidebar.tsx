"use client";

import { ChevronLeft, Workflow } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { Logo } from "@/components/shared/logo";
import { useMyWorkspace, useWorkspaceAccess } from "@/hooks/api/use-workspace";
import { DASHBOARD_NAV_GROUPS, permittedNavigation } from "@/lib/dashboard-nav";
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
  const { data: workspace } = useMyWorkspace();
  const { data: access } = useWorkspaceAccess(workspace?.id);
  const navigation = permittedNavigation(access?.capabilities);

  return (
    <aside
      className={cn(
        "hidden shrink-0 flex-col border-r border-border bg-card transition-[width] duration-200 md:flex",
        collapsed ? "w-[72px]" : "w-[248px]",
      )}
    >
      <div
        className={cn(
          "flex h-16 items-center border-b border-border",
          collapsed ? "justify-center px-2" : "px-5",
        )}
      >
        {collapsed ? (
          <span className="grid size-9 place-items-center rounded-lg bg-foreground text-background">
            <Workflow className="size-4" />
          </span>
        ) : (
          <Logo />
        )}
      </div>

      <nav className="flex flex-1 flex-col gap-4 overflow-y-auto p-3" aria-label={tShell("primaryNavigation")}>
        {DASHBOARD_NAV_GROUPS.map((group) => (
          <div key={group} className="space-y-1">
            {!collapsed ? (
              <p className="px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/80">
                {tShell(`navGroups.${group}`)}
              </p>
            ) : group !== "workspace" ? (
              <div aria-hidden className="mx-auto mb-2 h-px w-8 bg-border" />
            ) : null}
            {navigation.filter((item) => item.group === group).map((item) => {
              const active = isActive(pathname, item.href);
              const label = tNav(item.key);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  title={collapsed ? label : undefined}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "group relative flex min-h-10 items-center gap-3 rounded-md px-2.5 text-sm transition-colors",
                    active
                      ? "bg-brand-soft font-semibold text-brand"
                      : "font-medium text-muted-foreground hover:bg-muted hover:text-foreground",
                    collapsed && "justify-center px-0",
                  )}
                >
                  {active && !collapsed ? (
                    <span aria-hidden className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-brand" />
                  ) : null}
                  <item.icon className="size-[18px] shrink-0" />
                  {!collapsed && <span className="truncate">{label}</span>}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="border-t border-border p-3">
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? tShell("expand") : tShell("collapse")}
          className={cn(
            "flex w-full items-center gap-2 rounded-md border border-border py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
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
