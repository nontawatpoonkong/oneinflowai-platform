"use client";

import { useQuery } from "@tanstack/react-query";

import { auditService } from "@/services/audit/audit.service";
import type { AuditFilters } from "@/types/audit";

export function useAuditEvents(filters: AuditFilters, enabled = true) {
  return useQuery({
    queryKey: ["audit", "events", filters],
    queryFn: () => auditService.list(filters),
    enabled,
  });
}
