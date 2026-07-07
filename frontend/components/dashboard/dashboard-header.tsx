import { Bell, Search } from "lucide-react";

import { ThemeToggle } from "@/components/shared/theme-toggle";

export function DashboardHeader() {
  return (
    <header className="flex h-16 items-center justify-between gap-4 border-b border-border bg-card/60 px-4 backdrop-blur-xl sm:px-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Dashboard</h1>
        <p className="text-xs text-muted-foreground">Workspace overview</p>
      </div>
      <div className="flex items-center gap-2">
        <div className="hidden items-center gap-2 rounded-full border border-border bg-background px-3 py-2 text-sm text-muted-foreground sm:flex">
          <Search className="size-4" />
          <span>Search…</span>
        </div>
        <button
          type="button"
          aria-label="Notifications"
          className="grid size-9 place-items-center rounded-full border border-border text-muted-foreground transition-colors hover:text-foreground"
        >
          <Bell className="size-4" />
        </button>
        <ThemeToggle />
      </div>
    </header>
  );
}
