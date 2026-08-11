export type PaymentStatus = "PENDING" | "VERIFYING" | "VERIFIED" | "REJECTED" | "DUPLICATE" | "EXPIRED" | "REFUNDED";
export interface PaymentDTO {
  id: string; action_request_id: string | null; conversation_id: string | null;
  customer_id: string | null; payment_destination_id: string; status: PaymentStatus;
  expected_amount: string; verified_amount: string | null; currency: string;
  reference: string | null; paid_at: string | null; verified_at: string | null;
  expires_at: string | null; created_at: string; updated_at: string;
}
export interface PaymentDestinationDTO {
  id: string; type: "BANK_ACCOUNT" | "PROMPTPAY"; display_name: string;
  bank_name: string | null; account_name: string | null; account_number_masked: string | null;
  promptpay_identifier_last4: string | null; is_active: boolean; is_default: boolean;
}
