import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type { BookingPaymentExceptionDTO, PaymentDTO, PaymentDestinationDTO, PaymentEvidenceDTO, PaymentVerificationDTO } from "@/types/payment";
export const paymentService = {
  async list(): Promise<PaymentDTO[]> { return unwrap(await api.get<ApiEnvelope<PaymentDTO[]>>("/payments")); },
  async destinations(): Promise<PaymentDestinationDTO[]> { return unwrap(await api.get<ApiEnvelope<PaymentDestinationDTO[]>>("/payments/destinations")); },
  async evidence(id:string): Promise<PaymentEvidenceDTO> { return unwrap(await api.get<ApiEnvelope<PaymentEvidenceDTO>>(`/payments/${id}/evidence`)); },
  async verifications(id:string): Promise<PaymentVerificationDTO[]> { return unwrap(await api.get<ApiEnvelope<PaymentVerificationDTO[]>>(`/payments/${id}/verifications`)); },
  async bookingExceptions(): Promise<BookingPaymentExceptionDTO[]> { return unwrap(await api.get<ApiEnvelope<BookingPaymentExceptionDTO[]>>("/hotel/payment-exceptions")); },
  async reconcileBookingPayment(id:string): Promise<BookingPaymentExceptionDTO> { return unwrap(await api.post<ApiEnvelope<BookingPaymentExceptionDTO>>(`/hotel/payment-exceptions/${id}/reconcile`)); },
  async acknowledgeBookingPayment(id:string,note:string): Promise<BookingPaymentExceptionDTO> { return unwrap(await api.post<ApiEnvelope<BookingPaymentExceptionDTO>>(`/hotel/payment-exceptions/${id}/acknowledge`,{note})); },
};
