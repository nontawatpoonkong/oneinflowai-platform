"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { promotionService } from "@/services/promotion/promotion.service";

export function usePromotionData() {
  return {
    campaigns: useQuery({ queryKey: ["promotions", "campaigns"], queryFn: promotionService.campaigns }),
    promotions: useQuery({ queryKey: ["promotions", "rules"], queryFn: promotionService.promotions }),
    codes: useQuery({ queryKey: ["promotions", "codes"], queryFn: promotionService.codes }),
    redemptions: useQuery({ queryKey: ["promotions", "redemptions"], queryFn: promotionService.redemptions }),
    properties: useQuery({ queryKey: ["hotel", "properties"], queryFn: promotionService.properties }),
    roomTypes: useQuery({ queryKey: ["hotel", "room-types"], queryFn: promotionService.roomTypes }),
    ratePlans: useQuery({ queryKey: ["hotel", "rate-plans"], queryFn: promotionService.ratePlans }),
  };
}

export function usePromotionMutations() {
  const client = useQueryClient();
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["promotions"] }); };
  return {
    createCampaign: useMutation({ mutationFn: promotionService.createCampaign, onSuccess: refresh }),
    updateCampaign: useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof promotionService.updateCampaign>[1] }) => promotionService.updateCampaign(id, payload), onSuccess: refresh }),
    transitionCampaign: useMutation({ mutationFn: ({ id, action }: { id: string; action: "activate" | "pause" | "expire" | "archive" }) => promotionService.transitionCampaign(id, action), onSuccess: refresh }),
    createPromotion: useMutation({ mutationFn: promotionService.createPromotion, onSuccess: refresh }),
    updatePromotion: useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof promotionService.updatePromotion>[1] }) => promotionService.updatePromotion(id, payload), onSuccess: refresh }),
    createCode: useMutation({ mutationFn: promotionService.createCode, onSuccess: refresh }),
    transitionCode: useMutation({ mutationFn: ({ id, action }: { id: string; action: "enable" | "disable" | "archive" }) => promotionService.transitionCode(id, action), onSuccess: refresh }),
  };
}
