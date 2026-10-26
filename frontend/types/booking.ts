export type BookingStatus =
  | "DRAFT"
  | "HELD"
  | "PENDING_PAYMENT"
  | "CONFIRMED"
  | "CANCELLED"
  | "EXPIRED";

export interface BookingCatalogProperty {
  id: string;
  name: string;
  currency: string;
  timezone: string;
  active: boolean;
}

export interface BookingCatalogRoomType {
  id: string;
  property_id: string;
  name: string;
  max_adults: number;
  max_children: number;
  max_occupancy: number;
  active: boolean;
}

export interface BookingCatalogRatePlan {
  id: string;
  property_id: string;
  room_type_id: string;
  name: string;
  currency: string;
  base_price: string;
  refundable: boolean;
  active: boolean;
}

export interface ManualQuoteRequest {
  property_id: string;
  room_type_id: string;
  rate_plan_id: string;
  check_in: string;
  check_out: string;
  adults: number;
  children: number;
  quantity: number;
  customer_id: string | null;
  promotion_code: string | null;
}

export type ManualQuoteReason =
  | "OCCUPANCY_EXCEEDED"
  | "NOT_AVAILABLE"
  | "INSUFFICIENT_UNITS"
  | "RATE_CURRENCY_MISMATCH";

export interface ManualQuotePromotion {
  valid: boolean;
  reason_code: string | null;
  code?: string | null;
  promotion_name?: string | null;
  discount_type?: "PERCENTAGE" | "FIXED_AMOUNT" | null;
  discount_value?: string | null;
}

/** Server-calculated preview. Money is exact decimal strings; never recompute. */
export interface ManualQuote {
  available: boolean;
  reason_code: ManualQuoteReason | null;
  room_type_name: string;
  rate_plan_name: string;
  nights: number;
  quantity: number;
  currency: string;
  nightly_rates: Array<{ date: string; amount: string }>;
  unit_subtotal: string | null;
  subtotal: string | null;
  discount_amount: string | null;
  total: string | null;
  available_units: number;
  refundable: boolean;
  cancellation_policy_summary: string | null;
  hold_minutes: number;
  promotion: ManualQuotePromotion | null;
  notice: string;
}

export interface BookingHoldPayload {
  property_id: string;
  room_type_id: string;
  rate_plan_id: string;
  check_in: string;
  check_out: string;
  adults: number;
  children: number;
  quantity: number;
  customer_id: string | null;
  guest_name: string | null;
  promotion_code: string | null;
  idempotency_key: string;
}

export interface BookingRecord {
  id: string;
  status: BookingStatus;
  check_in: string;
  check_out: string;
  adults: number;
  children: number;
  currency: string;
  subtotal: string;
  discount_amount: string;
  total_amount: string;
  promotion_snapshot: Record<string, unknown> | null;
  hold_expires_at: string | null;
  source: string;
  guest_name: string | null;
  customer_id: string | null;
  property_name_snapshot: string;
  item: { room_type_name_snapshot: string; rate_plan_name_snapshot: string; quantity: number };
}
