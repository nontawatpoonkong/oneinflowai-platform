"use client";

import { useQuery } from "@tanstack/react-query";

import { dashboardService } from "@/services/dashboard/dashboard.service";

/** Fetches the dashboard overview. Exposes loading / error / data / refetch. */
export function useDashboard() {
  const query = useQuery({
    queryKey: ["dashboard", "overview"],
    queryFn: () => dashboardService.getOverview(),
  });

  return {
    data: query.data,
    loading: query.isLoading,
    error: query.error,
    refetch: query.refetch,
  };
}
