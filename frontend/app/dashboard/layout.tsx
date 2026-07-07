"use client";

import type { ReactNode } from "react";

import { AppShell } from "@/components/dashboard/shell/app-shell";
import { AuthGuard } from "@/components/dashboard/shell/auth-guard";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <AppShell>{children}</AppShell>
    </AuthGuard>
  );
}
