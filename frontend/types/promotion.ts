export type CampaignStatus = "DRAFT" | "ACTIVE" | "PAUSED" | "EXPIRED" | "ARCHIVED";
export type PromotionCodeStatus = "ACTIVE" | "DISABLED" | "EXHAUSTED" | "EXPIRED" | "ARCHIVED";
export type DiscountType = "PERCENTAGE" | "FIXED_AMOUNT";
export type PromotionSource = "DIRECT" | "WEBCHAT" | "LINE" | "FACEBOOK" | "INSTAGRAM" | "PARTNER" | "MANUAL" | "OTHER";

export interface PromotionCampaign {
  id: string; name: string; description: string | null; status: CampaignStatus;
  valid_from: string | null; valid_until: string | null; updated_at: string;
  management_origin?: "WORKSPACE" | "PLATFORM"; started_at?: string | null;
}
export interface PromotionRule {
  id: string; campaign_id: string; name: string; discount_type: DiscountType;
  discount_value: string; max_discount_amount: string | null; minimum_subtotal: string | null;
  currency: string | null; valid_from: string | null; valid_until: string | null;
  stay_date_start: string | null; stay_date_end: string | null; total_usage_limit: number | null;
  per_customer_limit: number | null; active: boolean; property_ids: string[];
  room_type_ids: string[]; rate_plan_ids: string[]; sources: PromotionSource[]; updated_at: string;
}
export interface PromotionCode {
  id: string; promotion_id: string; code: string; status: PromotionCodeStatus;
  usage_limit: number | null; created_at: string; updated_at: string;
}
export interface PromotionRedemption {
  id: string; promotion_id: string; promotion_code_id: string | null; customer_id: string | null;
  booking_id: string; discount_amount: string; currency: string; status: "RESERVED" | "CONFIRMED" | "RELEASED";
  reserved_until: string | null; redeemed_at: string | null; created_at: string;
}
export interface PromotionRulePayload {
  campaign_id: string; name: string; discount_type: DiscountType; discount_value: string;
  max_discount_amount: string | null; minimum_subtotal: string | null; currency: string | null;
  valid_from: string | null; valid_until: string | null; stay_date_start: string | null;
  stay_date_end: string | null; total_usage_limit: number | null; per_customer_limit: number | null;
  property_ids: string[]; room_type_ids: string[]; rate_plan_ids: string[]; sources: PromotionSource[];
}
export interface PromotionCatalogOption { id: string; name: string; property_id?: string; room_type_id?: string; }
