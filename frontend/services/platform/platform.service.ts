import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type {
  PlatformMutationPayload,
  PlatformOverview,
  PlatformPage,
  PlatformRecord,
} from "@/types/platform";

export const platformService = {
  async overview(): Promise<PlatformOverview> {
    return unwrap(
      await api.get<ApiEnvelope<PlatformOverview>>("/platform/overview"),
    );
  },
  async page(
    path: string,
    page = 1,
    pageSize = 25,
  ): Promise<PlatformPage<PlatformRecord>> {
    return unwrap(
      await api.get<ApiEnvelope<PlatformPage<PlatformRecord>>>(path, {
        params: { page, page_size: pageSize },
      }),
    );
  },
  async snapshot(path: string): Promise<PlatformRecord> {
    return unwrap(await api.get<ApiEnvelope<PlatformRecord>>(path));
  },
  async mutate(path: string, reason: string): Promise<PlatformRecord> {
    const payload: PlatformMutationPayload = { reason, confirmed: true };
    return unwrap(await api.post<ApiEnvelope<PlatformRecord>>(path, payload));
  },
};
