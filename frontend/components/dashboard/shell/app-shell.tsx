"use client";

import { useEffect, useState, type ReactNode } from "react";

import { AppSidebar } from "@/components/dashboard/shell/app-sidebar";
import { AppTopbar } from "@/components/dashboard/shell/app-topbar";
import { UsageTracker } from "@/components/dashboard/usage-tracker";

const STORAGE_KEY = "oneflow_sidebar_collapsed";

/** Reusable application shell: sidebar + topbar + content area. */
export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    setCollapsed(localStorage.getItem(STORAGE_KEY) === "true");
  }, []);

  function toggle() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(STORAGE_KEY, String(next));
      return next;
    });
  }

  return (
    <div className="app-workspace flex min-h-dvh bg-background">
      <UsageTracker />
      <AppSidebar collapsed={collapsed} onToggle={toggle} />
      <div className="flex min-w-0 flex-1 flex-col">
        <AppTopbar />
        <main className="flex-1 bg-surface/55 p-4 sm:p-6 lg:p-8">
          <div className="mx-auto w-full max-w-[1600px]">{children}</div>
        </main>
      </div>
    </div>
  );
}
