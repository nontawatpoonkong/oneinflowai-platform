import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type { PromotionCampaign, PromotionCatalogOption, PromotionCode, PromotionRedemption, PromotionRule, PromotionRulePayload } from "@/types/promotion";

export const promotionService = {
  campaigns: async (): Promise<PromotionCampaign[]> => unwrap(await api.get<ApiEnvelope<PromotionCampaign[]>>("/promotions/campaigns")),
  createCampaign: async (payload: { name: string; description: string | null; valid_from: string | null; valid_until: string | null }): Promise<PromotionCampaign> => unwrap(await api.post<ApiEnvelope<PromotionCampaign>>("/promotions/campaigns", payload)),
  updateCampaign: async (id: string, payload: Partial<PromotionCampaign>): Promise<PromotionCampaign> => unwrap(await api.patch<ApiEnvelope<PromotionCampaign>>(`/promotions/campaigns/${id}`, payload)),
  transitionCampaign: async (id: string, action: "activate" | "pause" | "expire" | "archive"): Promise<PromotionCampaign> => unwrap(await api.post<ApiEnvelope<PromotionCampaign>>(`/promotions/campaigns/${id}/${action}`)),
  promotions: async (): Promise<PromotionRule[]> => unwrap(await api.get<ApiEnvelope<PromotionRule[]>>("/promotions")),
  createPromotion: async (payload: PromotionRulePayload): Promise<PromotionRule> => unwrap(await api.post<ApiEnvelope<PromotionRule>>("/promotions", payload)),
  updatePromotion: async (id: string, payload: Partial<PromotionRulePayload>): Promise<PromotionRule> => unwrap(await api.patch<ApiEnvelope<PromotionRule>>(`/promotions/rules/${id}`, payload)),
  codes: async (): Promise<PromotionCode[]> => unwrap(await api.get<ApiEnvelope<PromotionCode[]>>("/promotions/codes")),
  createCode: async (payload: { promotion_id: string; code: string; usage_limit: number | null }): Promise<PromotionCode> => unwrap(await api.post<ApiEnvelope<PromotionCode>>("/promotions/codes", payload)),
  transitionCode: async (id: string, action: "enable" | "disable" | "archive"): Promise<PromotionCode> => unwrap(await api.post<ApiEnvelope<PromotionCode>>(`/promotions/codes/${id}/${action}`)),
  redemptions: async (): Promise<PromotionRedemption[]> => unwrap(await api.get<ApiEnvelope<PromotionRedemption[]>>("/promotions/redemptions")),
  properties: async (): Promise<PromotionCatalogOption[]> => unwrap(await api.get<ApiEnvelope<PromotionCatalogOption[]>>("/hotel/properties")),
  roomTypes: async (): Promise<PromotionCatalogOption[]> => unwrap(await api.get<ApiEnvelope<PromotionCatalogOption[]>>("/hotel/room-types")),
  ratePlans: async (): Promise<PromotionCatalogOption[]> => unwrap(await api.get<ApiEnvelope<PromotionCatalogOption[]>>("/hotel/rate-plans")),
};
