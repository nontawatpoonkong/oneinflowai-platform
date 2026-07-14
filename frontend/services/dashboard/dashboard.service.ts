import { api } from "@/services/api/client";

/** Response shape of GET /dashboard/overview. */
export interface DashboardOverview {
  today_conversations: number;
  new_customers: number;
  ai_reply_rate: number;
  avg_response_time: number;
  saving_hours: number;
  saving_cost: number;
  /** Optional insight fields; may be absent until the backend provides them. */
  peak_hour?: string | number;
  recommendation?: string;
}

/** Dashboard API access. Responsible only for calling the backend. */
export const dashboardService = {
  async getOverview(): Promise<DashboardOverview> {
    const response = await api.get<DashboardOverview>("/dashboard/overview");
    return response.data;
  },
};
