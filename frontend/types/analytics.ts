export interface AnalyticsPoint { date: string; count: number }
export interface AnalyticsCount { key: string; label: string | null; count: number }
export interface AnalyticsOverview {
  range: { start: string; end: string; timezone: "UTC" };
  kpis: Record<string, number>;
  conversation_trend: AnalyticsPoint[];
  conversations_by_channel: AnalyticsCount[];
  message_counts: AnalyticsCount[];
  handoff_reasons: AnalyticsCount[];
  actions_by_type: AnalyticsCount[];
  action_statuses: AnalyticsCount[];
  payment_statuses: AnalyticsCount[];
  verified_amounts: { currency: string; amount: string }[];
  verification_statuses: AnalyticsCount[];
  current_queue: Record<string, number>;
}
