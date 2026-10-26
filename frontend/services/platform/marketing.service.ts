import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type {
  CampaignAnalytics,
  CampaignDetail,
  CampaignListItem,
  CatalogTarget,
  CodeListItem,
  PlatformPage,
  PlatformRecord,
} from "@/types/platform";

type Params = Record<string, string | number | undefined>;
const clean = (params: Params) =>
  Object.fromEntries(Object.entries(params).filter(([, value]) => value !== undefined && value !== ""));

export const platformMarketingService = {
  campaigns: async (params: Params): Promise<PlatformPage<CampaignListItem>> =>
    unwrap(await api.get<ApiEnvelope<PlatformPage<CampaignListItem>>>("/platform/marketing/campaigns", { params: clean(params) })),
  codes: async (params: Params): Promise<PlatformPage<CodeListItem>> =>
    unwrap(await api.get<ApiEnvelope<PlatformPage<CodeListItem>>>("/platform/marketing/codes", { params: clean(params) })),
  campaign: async (id: string): Promise<CampaignDetail> =>
    unwrap(await api.get<ApiEnvelope<CampaignDetail>>(`/platform/marketing/campaigns/${id}`)),
  catalog: async (id: string, params: Params): Promise<PlatformPage<CatalogTarget>> =>
    unwrap(await api.get<ApiEnvelope<PlatformPage<CatalogTarget>>>(`/platform/marketing/campaigns/${id}/catalog`, { params: clean(params) })),
  analytics: async (start: string, end: string): Promise<CampaignAnalytics> =>
    unwrap(await api.get<ApiEnvelope<CampaignAnalytics>>("/platform/marketing/analytics", { params: { start, end } })),
  workspaces: async (search: string): Promise<PlatformPage<PlatformRecord>> =>
    unwrap(await api.get<ApiEnvelope<PlatformPage<PlatformRecord>>>("/platform/workspaces", { params: clean({ search, page_size: 10, status: "ACTIVE" }) })),
  createCampaign: async (payload: Record<string, unknown>): Promise<CampaignDetail> =>
    unwrap(await api.post<ApiEnvelope<CampaignDetail>>("/platform/marketing/campaigns", payload)),
  updateCampaign: async (id: string, payload: Record<string, unknown>): Promise<CampaignDetail> =>
    unwrap(await api.patch<ApiEnvelope<CampaignDetail>>(`/platform/marketing/campaigns/${id}`, payload)),
  addRule: async (id: string, payload: Record<string, unknown>): Promise<CampaignDetail> =>
    unwrap(await api.post<ApiEnvelope<CampaignDetail>>(`/platform/marketing/campaigns/${id}/rules`, payload)),
  addCode: async (id: string, payload: Record<string, unknown>): Promise<CampaignDetail> =>
    unwrap(await api.post<ApiEnvelope<CampaignDetail>>(`/platform/marketing/campaigns/${id}/codes`, payload)),
  transitionCampaign: async (id: string, verb: "pause" | "expire" | "archive", reason: string) =>
    unwrap(await api.post<ApiEnvelope<PlatformRecord>>(`/platform/marketing/campaigns/${id}/${verb}`, { reason, confirmed: true })),
  transitionCode: async (id: string, verb: "disable" | "archive", reason: string) =>
    unwrap(await api.post<ApiEnvelope<PlatformRecord>>(`/platform/marketing/codes/${id}/${verb}`, { reason, confirmed: true })),
};
