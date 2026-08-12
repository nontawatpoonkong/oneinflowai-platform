import { api, unwrap } from "@/services/api/client";
import type { AnalyticsOverview } from "@/types/analytics";
import type { ApiEnvelope } from "@/types/api";

export const analyticsService = {
  async overview(days: number): Promise<AnalyticsOverview> {
    const end = new Date();
    const start = new Date(end.getTime() - days * 86_400_000);
    return unwrap(await api.get<ApiEnvelope<AnalyticsOverview>>("/analytics/overview", {
      params: { start: start.toISOString(), end: end.toISOString() },
    }));
  },
};
