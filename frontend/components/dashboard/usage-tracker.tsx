"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { useMyWorkspace } from "@/hooks/api/use-workspace";
import {
  usageService,
  type ProductFeature,
} from "@/services/analytics/usage.service";

const SESSION_KEY = "oneinflow_usage_session";

function featureFor(pathname: string): ProductFeature {
  if (pathname === "/dashboard") return "HOME";
  if (pathname.startsWith("/dashboard/inbox")) return "CONVERSATIONS";
  if (pathname.startsWith("/dashboard/customers")) return "GUESTS";
  if (pathname.startsWith("/dashboard/payments")) return "PAYMENTS";
  if (pathname.startsWith("/dashboard/bookings")) return "BOOKINGS";
  if (pathname.startsWith("/dashboard/hotel/availability")) return "AVAILABILITY";
  if (pathname.startsWith("/dashboard/hotel/catalog")) return "ROOMS";
  if (pathname.startsWith("/dashboard/hotel/rooms")) return "ROOMS";
  if (pathname.startsWith("/dashboard/hotel/stays")) return "STAYS";
  if (pathname.startsWith("/dashboard/hotel/housekeeping")) return "HOUSEKEEPING";
  if (pathname.startsWith("/dashboard/automations")) return "AUTOMATIONS";
  if (pathname.startsWith("/dashboard/hotel/pms")) return "PMS";
  if (pathname.startsWith("/dashboard/analytics")) return "ANALYTICS";
  if (pathname.startsWith("/dashboard/promotions")) return "PROMOTIONS";
  if (pathname.startsWith("/dashboard/knowledge")) return "KNOWLEDGE";
  if (pathname.startsWith("/dashboard/settings/team")) return "TEAM";
  return "SETTINGS";
}

function sessionId(): string {
  const existing = sessionStorage.getItem(SESSION_KEY);
  if (existing) return existing;
  const created = crypto.randomUUID();
  sessionStorage.setItem(SESSION_KEY, created);
  return created;
}

export function UsageTracker() {
  const pathname = usePathname();
  const workspace = useMyWorkspace();
  const lastOccurrence = useRef<string | null>(null);

  useEffect(() => {
    if (!workspace.data || !pathname.startsWith("/dashboard")) return;
    const occurrence = `${workspace.data.id}:${pathname}`;
    if (lastOccurrence.current === occurrence) return;
    lastOccurrence.current = occurrence;

    // Telemetry is deliberately best-effort: a failure must never block the page.
    void usageService
      .pageView({
        navigation_id: crypto.randomUUID(),
        session_id: sessionId(),
        page_path: pathname,
        feature: featureFor(pathname),
        occurred_at: new Date().toISOString(),
      })
      .catch(() => undefined);
  }, [pathname, workspace.data]);

  return null;
}
