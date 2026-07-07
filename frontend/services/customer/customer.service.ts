import { api, unwrap } from "@/services/api/client";
import type {
  ApiEnvelope,
  CustomerDTO,
  ListParams,
  Paginated,
} from "@/types/api";

export const customerService = {
  async list(params: ListParams = {}): Promise<Paginated<CustomerDTO>> {
    const res = await api.get<ApiEnvelope<Paginated<CustomerDTO>>>("/customers", {
      params,
    });
    return unwrap(res);
  },
};
