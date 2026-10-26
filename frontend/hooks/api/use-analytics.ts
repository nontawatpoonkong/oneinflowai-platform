"use client";

import { useQuery } from "@tanstack/react-query";

import { analyticsService } from "@/services/analytics/analytics.service";
import type { AnalyticsQueryRange } from "@/types/analytics";

export function useAnalytics(range: AnalyticsQueryRange) {
  return useQuery({
    queryKey: ["analytics", "overview", range],
    queryFn: () => analyticsService.overview(range),
  });
}
