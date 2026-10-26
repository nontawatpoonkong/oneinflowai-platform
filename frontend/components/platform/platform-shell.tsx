"use client";

import {
  Activity,
  BarChart3,
  Building2,
  ClipboardList,
  CreditCard,
  LayoutDashboard,
  Megaphone,
  ServerCog,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";

const navigation = [
  ["Overview", "/platform", LayoutDashboard],
  ["Users", "/platform/users", Users],
  ["Workspaces", "/platform/workspaces", Building2],
  ["Subscriptions", "/platform/subscriptions", CreditCard],
  ["Marketing", "/platform/marketing", Megaphone],
  ["Analytics", "/platform/analytics", BarChart3],
  ["Operations", "/platform/operations", Activity],
  ["Audit", "/platform/audit", ClipboardList],
  ["System", "/platform/system", ServerCog],
] as const;

export function PlatformShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  return (
    <div className="min-h-dvh bg-background text-foreground lg:grid lg:grid-cols-[240px_1fr]">
      <aside className="border-b border-cyan-500/20 bg-card lg:min-h-dvh lg:border-b-0 lg:border-r">
        <div className="flex h-16 items-center justify-between border-b px-5">
          <Link href="/platform" className="font-semibold tracking-tight">
            OneInFlowAI <span className="text-cyan-500">Platform</span>
          </Link>
        </div>
        <nav aria-label="Platform Console" className="flex gap-1 overflow-x-auto p-3 lg:flex-col">
          {navigation.map(([label, href, Icon]) => {
            const active = href === "/platform" ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex shrink-0 items-center gap-3 rounded-md px-3 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500",
                  active
                    ? "border border-pink-500/35 bg-cyan-500/10 text-cyan-600 dark:text-cyan-300"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="min-w-0">
        <header className="flex h-16 items-center justify-between border-b bg-card/80 px-4 backdrop-blur lg:px-7">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-600">Internal operations</p>
            <p className="text-sm text-muted-foreground">Cross-tenant controls are audited</p>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden text-muted-foreground sm:inline">{user?.email}</span>
            <Button variant="outline" size="sm" onClick={logout}>Sign out</Button>
          </div>
        </header>
        <main className="p-4 lg:p-7">{children}</main>
      </div>
    </div>
  );
}
