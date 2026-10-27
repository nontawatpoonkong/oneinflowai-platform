export interface AnalyticsPoint { date: string; count: number }
export interface AnalyticsCount { key: string; label: string | null; count: number }
export interface MoneyTotal { currency: string; amount: string }
export interface PromotionMoney {
  currency: string; uses: number; gross_amount: string; discount_amount: string; net_amount: string;
}
export interface PromotionDimension {
  key: string; label?: string | null; currency: string; uses: number; discount_amount: string; net_amount: string;
}

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
  verified_amounts: MoneyTotal[];
  verification_statuses: AnalyticsCount[];
  current_queue: Record<string, number>;
  sales: {
    booking_counts: Record<string, number>;
    confirmed_value_by_currency: MoneyTotal[];
    average_confirmed_value_by_currency: MoneyTotal[];
    payment_requires_review: number;
    funnel: { attribution_supported: false; unsupported_stages: string[]; hold: number; payment_initiated: number; confirmed: number };
    promotions: {
      redemptions: number;
      by_currency: PromotionMoney[];
      campaigns: PromotionDimension[];
      codes: PromotionDimension[];
      sources: PromotionDimension[];
      properties: PromotionDimension[];
      campaigns_by_status: Record<string, number>;
      codes_by_status: Record<string, number>;
      reservation_funnel: { reserved: number; confirmed: number; released: number; definition: string };
      daily_trend: Array<{ date: string; currency: string; uses: number; discount_amount: string }>;
      definition: string;
    };
  };
  operations: {
    stays: Record<string, number>;
    room_readiness: Record<string, number>;
    housekeeping_completed: number;
    housekeeping_turnaround_minutes: number | null;
    turnaround_definition: string;
  };
  ai_conversations: {
    tool_actions: number;
    tool_action_statuses: Record<string, number>;
    tool_actions_succeeded: number;
    tool_actions_failed: number;
    human_handoffs: number;
    privacy: string;
  };
  automation: {
    execution_count: number;
    statuses: Record<string, number>;
    success_rate: number;
    retry_rate: number;
    average_attempts: number;
    terminal_failed: number;
    most_used: AnalyticsCount[];
  };
  usage: {
    page_views: number;
    unique_active_users: number;
    home_views: number;
    home_unique_users: number;
    feature_usage: AnalyticsCount[];
    home_views_by_day: AnalyticsPoint[];
    recent_home_viewers: Array<{ user_id: string; name: string; last_viewed_at: string; views: number }>;
    privacy: string;
  };
}

export interface AnalyticsQueryRange { start: string; end: string }
