import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";

export type ProductFeature =
  | "HOME"
  | "CONVERSATIONS"
  | "GUESTS"
  | "BOOKINGS"
  | "PAYMENTS"
  | "AVAILABILITY"
  | "ROOMS"
  | "STAYS"
  | "HOUSEKEEPING"
  | "AUTOMATIONS"
  | "PMS"
  | "ANALYTICS"
  | "PROMOTIONS"
  | "KNOWLEDGE"
  | "TEAM"
  | "SETTINGS";

interface UsageEventResponse {
  id: string;
  event_name: "PAGE_VIEW";
  page_path: string;
  feature: ProductFeature;
  occurred_at: string;
}

export const usageService = {
  async pageView(payload: {
    navigation_id: string;
    session_id: string;
    page_path: string;
    feature: ProductFeature;
    occurred_at: string;
  }): Promise<UsageEventResponse> {
    return unwrap(
      await api.post<ApiEnvelope<UsageEventResponse>>("/analytics/events", {
        event_name: "PAGE_VIEW",
        safe_properties: {},
        ...payload,
      }),
    );
  },
};
