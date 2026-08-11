import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope, Paginated } from "@/types/api";
import type { ActionDTO, ActionDefinitionDTO, ActionDefinitionInput, ActionDefinitionUpdate, ActionPriority, ActionStatus } from "@/types/action";

export interface ActionFilters { status?: ActionStatus; priority?: ActionPriority; assigned_to?: string; page?: number; page_size?: number }
export const actionService = {
  async list(params: ActionFilters = {}): Promise<Paginated<ActionDTO>> {
    return unwrap(await api.get<ApiEnvelope<Paginated<ActionDTO>>>("/actions", { params }));
  },
  async definitions(): Promise<ActionDefinitionDTO[]> {
    return unwrap(await api.get<ApiEnvelope<ActionDefinitionDTO[]>>("/actions/definitions"));
  },
  async createDefinition(payload: ActionDefinitionInput): Promise<ActionDefinitionDTO> {
    return unwrap(await api.post<ApiEnvelope<ActionDefinitionDTO>>("/actions/definitions", payload));
  },
  async updateDefinition(id: string, payload: ActionDefinitionUpdate): Promise<ActionDefinitionDTO> {
    return unwrap(await api.patch<ApiEnvelope<ActionDefinitionDTO>>(`/actions/definitions/${encodeURIComponent(id)}`, payload));
  },
  async assign(id: string, userId: string): Promise<ActionDTO> {
    return unwrap(await api.post<ApiEnvelope<ActionDTO>>(`/actions/${encodeURIComponent(id)}/assign`, { user_id: userId }));
  },
  async transition(id: string, transition: "start" | "complete" | "fail" | "cancel"): Promise<ActionDTO> {
    return unwrap(await api.post<ApiEnvelope<ActionDTO>>(`/actions/${encodeURIComponent(id)}/${transition}`));
  },
};
