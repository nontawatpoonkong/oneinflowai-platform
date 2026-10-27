export interface PlatformPage<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export type PlatformRecord = Record<string, unknown> & { id?: string };

export interface PlatformOverview {
  metrics: Record<string, unknown>;
  needs_attention: Record<string, number>;
  links: Record<string, string>;
}

export interface PlatformMutationPayload {
  reason: string;
  confirmed: true;
}

export type CampaignStatus = "DRAFT" | "ACTIVE" | "PAUSED" | "EXPIRED" | "ARCHIVED";
export type CodeStatus = "ACTIVE" | "DISABLED" | "EXHAUSTED" | "EXPIRED" | "ARCHIVED";

export interface CampaignListItem {
  id: string;
  workspace_id: string;
  workspace: string;
  name: string;
  description: string | null;
  status: CampaignStatus;
  origin: "WORKSPACE" | "PLATFORM";
  funding: "WORKSPACE";
  valid_from: string | null;
  valid_until: string | null;
  started_at: string | null;
  codes: number;
  confirmed_uses: number;
  active_reservations: number;
  updated_at: string;
}

export interface CodeListItem {
  id: string;
  code: string;
  status: CodeStatus;
  promotion_id: string;
  usage_limit: number | null;
  effective_limit: number | null;
  confirmed_uses: number;
  counted_uses: number;
  rule_uses?: number;
  remaining: number | null;
  discount: { type: string; value: string; currency: string | null };
  workspace_id: string;
  workspace: string;
  campaign: { id: string; name: string; status: CampaignStatus };
  updated_at: string;
}

export interface CampaignRule {
  id: string;
  name: string;
  discount_type: "PERCENTAGE" | "FIXED_AMOUNT";
  discount_value: string;
  max_discount_amount: string | null;
  minimum_subtotal: string | null;
  currency: string | null;
  valid_from: string | null;
  valid_until: string | null;
  stay_date_start: string | null;
  stay_date_end: string | null;
  total_usage_limit: number | null;
  per_customer_limit: number | null;
  active: boolean;
  eligibility: { property_ids: string[]; room_type_ids: string[]; rate_plan_ids: string[]; sources: string[] };
}

export type CatalogTargetKind = "property" | "room_type" | "rate_plan";

export interface CatalogTarget {
  id: string;
  kind: CatalogTargetKind;
  name: string;
  code: string | null;
  active: boolean;
  property_id: string | null;
  room_type_id: string | null;
  currency: string | null;
}

export interface CampaignDetail {
  campaign: Omit<CampaignListItem, "workspace" | "codes" | "confirmed_uses" | "active_reservations">;
  workspace: { id: string; name: string; status: string };
  funding: { owner: string; discount_borne_by: string; platform_funded: boolean; cross_workspace_redemption: boolean; note: string };
  allowed_operations: string[];
  editable_fields: string[];
  rules: CampaignRule[];
  target_labels: Record<string, { name: string; active: boolean }>;
  codes: CodeListItem[];
  redemptions: Array<{ status: string; currency: string; count: number; discount_amount: string }>;
  confirmed_booking_value: Array<{ currency: string; bookings: number; gross_amount: string; discount_granted: string; net_amount: string }>;
  audit: Array<{ id: string; action: string; actor_type: string; actor_email: string | null; resource_type: string; result: string; safe_metadata: Record<string, unknown>; occurred_at: string }>;
}

export interface LifecycleStatus {
  health: "HEALTHY" | "DEGRADED" | "STALE" | "NOT_RUNNING";
  alerts: string[];
  last_succeeded_at: string | null;
  last_failed_at: string | null;
  last_error_code: string | null;
  consecutive_failures: number;
  total_runs: number;
  total_processed: number;
  total_failures: number;
  overdue_expiry: number;
  overdue_start: number;
}

export interface CampaignAnalytics {
  range: { start: string; end: string; timezone: string };
  campaigns_by_status: Record<string, number>;
  codes_by_status: Record<string, number>;
  campaigns_by_origin: Record<string, number>;
  validations: { available: boolean; reason: string };
  reservation_funnel: { reserved: number; confirmed: number; released: number; active_reservations: number; definition: string };
  confirmed_by_currency: Array<{ currency: string; redemptions: number; gross_amount: string; discount_granted: string; net_amount: string }>;
  daily_trend: Array<{ date: string; currency: string; redemptions: number; discount_granted: string }>;
  top_workspaces: Array<{ workspace_id: string; workspace: string; currency: string; redemptions: number; discount_granted: string; net_amount: string }>;
  top_campaigns: Array<{ campaign_id: string; campaign: string; workspace: string; currency: string; redemptions: number; discount_granted: string; net_amount: string }>;
  by_source: Array<{ source: string; currency: string; redemptions: number; discount_granted: string }>;
  campaign_cost: { available: boolean; reason: string };
  lifecycle: LifecycleStatus;
  definition: string;
}
