import type { ChannelDTO } from "@/types/api";
import type { PaymentStatus } from "@/types/payment";

export type PreferenceKey = "preferred_room_type" | "bed_preference" | "smoking_preference" | "accessibility_request" | "arrival_preference" | "language" | "other";
export type PreferenceSource = "CUSTOMER_PROVIDED" | "STAFF_CONFIRMED" | "IMPORT";
export interface CRMCustomer { id:string; display_name:string; full_name:string|null; phone:string|null; email:string|null; avatar_url:string|null; status:string; created_at:string; updated_at:string; }
export interface CRMTag { id:string; name:string; normalized_name:string; created_at:string; }
export interface CRMPreference { id:string; key:PreferenceKey; value:string; source:PreferenceSource; confirmed_by_user_id:string|null; created_at:string; updated_at:string; }
export interface CRMNote { id:string; body:string; created_by_user_id:string|null; created_at:string; }
export interface CRMIdentity { id:string; channel:ChannelDTO; external_username:string|null; created_at:string; }
export interface CRMConversation { id:string; channel:ChannelDTO; status:string; ai_mode:"AUTO"|"COPILOT"|"HUMAN"; assigned_user_id:string|null; last_message_at:string|null; needs_attention:boolean; unread:boolean; preview:string|null; }
export interface CRMBooking { id:string; property_name:string; room_type_name:string|null; check_in:string; check_out:string; status:string; total_amount:string; currency:string; created_at:string; confirmed_at:string|null; }
export interface CRMPayment { id:string; booking_id:string|null; expected_amount:string; verified_amount:string|null; currency:string; status:PaymentStatus; application_status:"UNAPPLIED"|"APPLIED"|"REQUIRES_REVIEW"|null; application_reason:string|null; created_at:string; verified_at:string|null; booking_applied_at:string|null; }
export interface CRMPaymentException { payment_id:string; booking_id:string|null; reason:string|null; verified_amount:string|null; currency:string; verified_at:string|null; }
export interface CRMStay { id:string; booking_id:string; property_name:string; room_codes:string[]; planned_check_in_date:string; planned_check_out_date:string; actual_check_in_at:string|null; actual_check_out_at:string|null; status:string; }
export interface RepeatGuestSummary { repeat_guest:boolean; confirmed_bookings:number; cancelled_bookings:number; latest_booking_date:string|null; }
export interface Customer360 { customer:CRMCustomer; identities:CRMIdentity[]; tags:CRMTag[]; preferences:CRMPreference[]; notes:CRMNote[]; conversations:CRMConversation[]; bookings:CRMBooking[]; payments:CRMPayment[]; payment_exceptions:CRMPaymentException[]; stays:CRMStay[]; repeat_guest_summary:RepeatGuestSummary; }
export interface CRMCustomerListItem { customer:CRMCustomer; tags:CRMTag[]; booking_count:number; confirmed_bookings:number; repeat_guest:boolean; latest_booking_status:string|null; has_payment_exception:boolean; last_conversation_at:string|null; needs_attention:boolean; }
export interface CRMPaginated<T> { items:T[]; total:number; page:number; page_size:number; total_pages:number; }
export interface CRMTimelineEvent { id:string; type:string; occurred_at:string; entity_type:string; entity_id:string; summary:string; metadata:Record<string,string|number|boolean|null>; }
export interface CRMListParams { q?:string; tag_id?:string; has_active_booking?:boolean; has_payment_exception?:boolean; repeat_guest?:boolean; needs_attention?:boolean; page?:number; page_size?:number; }
