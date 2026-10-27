"use client";

import type { ReactNode } from "react";

import { PlatformGuard } from "@/components/platform/platform-guard";
import { PlatformShell } from "@/components/platform/platform-shell";

export default function PlatformLayout({ children }: { children: ReactNode }) {
  return <PlatformGuard><PlatformShell>{children}</PlatformShell></PlatformGuard>;
}
