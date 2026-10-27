import { api, unwrap } from "@/services/api/client";
import type { AnalyticsOverview, AnalyticsQueryRange } from "@/types/analytics";
import type { ApiEnvelope } from "@/types/api";

export const analyticsService = {
  async overview(range: AnalyticsQueryRange): Promise<AnalyticsOverview> {
    return unwrap(await api.get<ApiEnvelope<AnalyticsOverview>>("/analytics/overview", {
      params: range,
    }));
  },
};
