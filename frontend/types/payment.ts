export type PaymentStatus = "PENDING" | "VERIFYING" | "VERIFIED" | "REJECTED" | "DUPLICATE" | "EXPIRED" | "REFUNDED";
export type BookingPaymentApplicationStatus = "UNAPPLIED" | "APPLIED" | "REQUIRES_REVIEW";
export type BookingPaymentExceptionReason = "BOOKING_EXPIRED" | "BOOKING_CANCELLED" | "BOOKING_ALREADY_CONFIRMED" | "AMOUNT_MISMATCH" | "CURRENCY_MISMATCH" | "PAYMENT_ALREADY_APPLIED" | "BOOKING_LINK_CONFLICT" | "INVALID_BOOKING_STATE" | "PAYMENT_NOT_VERIFIED";
export interface PaymentDTO {
  id: string; booking_id: string | null; booking_applied_at: string | null;
  booking_application_status: BookingPaymentApplicationStatus | null;
  booking_application_reason: BookingPaymentExceptionReason | null;
  booking_review_note: string | null; booking_reviewed_at: string | null;
  action_request_id: string | null; conversation_id: string | null;
  customer_id: string | null; payment_destination_id: string; status: PaymentStatus;
  expected_amount: string; verified_amount: string | null; currency: string;
  reference: string | null; paid_at: string | null; verified_at: string | null;
  expires_at: string | null; created_at: string; updated_at: string;
}
export interface BookingPaymentExceptionDTO {
  payment_id: string; booking_id: string; customer_id: string | null;
  payment_status: PaymentStatus;
  application_status: BookingPaymentApplicationStatus | null;
  reason: BookingPaymentExceptionReason | null;
  booking_status: "DRAFT" | "HELD" | "PENDING_PAYMENT" | "CONFIRMED" | "CANCELLED" | "EXPIRED";
  payment_expected_amount: string; payment_verified_amount: string | null;
  payment_currency: string; booking_total_amount: string; booking_currency: string;
  payment_verified_at: string | null; booking_hold_expires_at: string | null;
  review_note: string | null; reviewed_at: string | null;
}
export interface PaymentDestinationDTO {
  id: string; type: "BANK_ACCOUNT" | "PROMPTPAY"; display_name: string;
  bank_name: string | null; account_name: string | null; account_number_masked: string | null;
  promptpay_identifier_last4: string | null; is_active: boolean; is_default: boolean;
}
export interface PaymentEvidenceDTO {
  id: string; payment_id: string; mime_type: string; file_size: number;
  content_hash: string; created_at: string;
}
export interface PaymentVerificationDTO {
  id: string; payment_id: string; evidence_id: string; provider: string;
  provider_reference: string | null; status: "PENDING" | "PROCESSING" | "VALID" | "INVALID" | "ERROR";
  reported_amount: string | null; currency: string | null;
  transfer_reference: string | null; transferred_at: string | null;
  receiver_match: boolean | null; amount_match: boolean | null;
  error_code: string | null; verified_at: string | null; created_at: string;
}
