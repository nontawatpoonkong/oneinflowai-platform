"use client";

import { Breadcrumbs } from "@/components/dashboard/shell/breadcrumbs";
import { MobileSidebar } from "@/components/dashboard/shell/mobile-sidebar";
import { Notifications } from "@/components/dashboard/shell/notifications";
import { ProfileMenu } from "@/components/dashboard/shell/profile-menu";
import { WorkspaceSelector } from "@/components/dashboard/shell/workspace-selector";
import { ThemeToggle } from "@/components/shared/theme-toggle";

export function AppTopbar() {
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-border bg-background/95 px-4 backdrop-blur sm:px-6">
      {/* Left: workspace takes the lead, then breadcrumbs. */}
      <div className="flex min-w-0 items-center gap-2 sm:gap-3">
        <MobileSidebar />
        <WorkspaceSelector />
        <span aria-hidden className="hidden h-6 w-px bg-border lg:block" />
        <div className="hidden min-w-0 lg:block">
          <Breadcrumbs />
        </div>
      </div>

      {/* Right: real operational controls only. */}
      <div className="flex shrink-0 items-center gap-2">
        <Notifications />
        <span aria-hidden className="hidden h-6 w-px bg-border sm:block" />
        <div className="hidden sm:block">
          <ThemeToggle />
        </div>
        <ProfileMenu />
      </div>
    </header>
  );
}
