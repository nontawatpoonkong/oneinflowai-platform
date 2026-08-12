"use client";

import { useQuery } from "@tanstack/react-query";

import { analyticsService } from "@/services/analytics/analytics.service";

export function useAnalytics(days: number) {
  return useQuery({
    queryKey: ["analytics", "overview", days],
    queryFn: () => analyticsService.overview(days),
  });
}
