"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Logo } from "@/components/shared/logo";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import { Button } from "@/components/ui/button";
import { useMyWorkspace, useWorkspaceAccess } from "@/hooks/api/use-workspace";
import { DASHBOARD_NAV_GROUPS, permittedNavigation } from "@/lib/dashboard-nav";
import { cn } from "@/lib/utils";

export function MobileSidebar() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const tNav = useTranslations("dashboard.nav");
  const tShell = useTranslations("dashboard.shell");
  const { data: workspace } = useMyWorkspace();
  const { data: access } = useWorkspaceAccess(workspace?.id);
  const navigation = permittedNavigation(access?.capabilities);

  return (
    <div className="md:hidden">
      <Button
        variant="ghost"
        size="icon"
        aria-label={tShell("openMenu")}
        onClick={() => setOpen(true)}
      >
        <Menu className="size-5" />
      </Button>

      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-foreground/30"
            onClick={() => setOpen(false)}
          >
            <motion.aside
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 260, damping: 30 }}
              onClick={(e) => e.stopPropagation()}
              role="dialog"
              aria-modal="true"
              aria-label={tShell("primaryNavigation")}
              className="flex h-full w-[min(88vw,320px)] flex-col gap-2 border-r border-border bg-card p-4 shadow-xl"
            >
              <div className="flex items-center justify-between px-1 py-2">
                <Logo />
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={tShell("closeMenu")}
                  onClick={() => setOpen(false)}
                >
                  <X className="size-5" />
                </Button>
              </div>
              <nav className="flex flex-col gap-4 overflow-y-auto py-2">
                {DASHBOARD_NAV_GROUPS.map((group) => (
                  <div key={group} className="space-y-1">
                    <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                      {tShell(`navGroups.${group}`)}
                    </p>
                    {navigation.filter((item) => item.group === group).map((item) => {
                      const active = item.href === "/dashboard" ? pathname === "/dashboard" : pathname.startsWith(item.href);
                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          onClick={() => setOpen(false)}
                          aria-current={active ? "page" : undefined}
                          className={cn(
                            "flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors",
                            active ? "bg-brand-soft text-brand" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                          )}
                        >
                          <item.icon className="size-[18px]" />
                          {tNav(item.key)}
                        </Link>
                      );
                    })}
                  </div>
                ))}
              </nav>
              <div className="mt-auto flex items-center justify-between border-t border-border pt-4">
                <span className="text-xs font-medium text-muted-foreground">{tShell("theme")}</span>
                <ThemeToggle />
              </div>
            </motion.aside>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
