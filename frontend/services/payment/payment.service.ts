import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type { PaymentDTO, PaymentDestinationDTO } from "@/types/payment";
export const paymentService = {
  async list(): Promise<PaymentDTO[]> { return unwrap(await api.get<ApiEnvelope<PaymentDTO[]>>("/payments")); },
  async destinations(): Promise<PaymentDestinationDTO[]> { return unwrap(await api.get<ApiEnvelope<PaymentDestinationDTO[]>>("/payments/destinations")); },
};
