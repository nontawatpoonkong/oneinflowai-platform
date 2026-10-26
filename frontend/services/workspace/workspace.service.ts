import { api, unwrap } from "@/services/api/client";
import type {
  ApiEnvelope,
  WorkspaceAccessDTO,
  WorkspaceAccessRequestDTO,
  WorkspaceAIInstructionsDTO,
  WorkspaceDTO,
  WorkspaceJoinSettingsDTO,
  WorkspaceMemberDTO,
} from "@/types/api";

export const workspaceService = {
  async me(): Promise<WorkspaceDTO> {
    const res = await api.get<ApiEnvelope<WorkspaceDTO>>("/workspaces/me");
    return unwrap(res);
  },

  async list(): Promise<WorkspaceDTO[]> {
    const res = await api.get<ApiEnvelope<WorkspaceDTO[]>>("/workspaces");
    return unwrap(res);
  },
  async create(payload: { name: string; subscriptionId: string }): Promise<WorkspaceDTO> {
    const res = await api.post<ApiEnvelope<WorkspaceDTO>>("/workspaces", {
      name: payload.name,
      subscription_id: payload.subscriptionId,
    });
    return unwrap(res);
  },
  async aiInstructions(workspaceId: string): Promise<WorkspaceAIInstructionsDTO> {
    const res = await api.get<ApiEnvelope<WorkspaceAIInstructionsDTO>>(
      `/workspaces/${encodeURIComponent(workspaceId)}/ai-instructions`,
    );
    return unwrap(res);
  },
  async updateAIInstructions(workspaceId: string, instructions: string): Promise<WorkspaceAIInstructionsDTO> {
    const res = await api.put<ApiEnvelope<WorkspaceAIInstructionsDTO>>(
      `/workspaces/${encodeURIComponent(workspaceId)}/ai-instructions`,
      { instructions },
    );
    return unwrap(res);
  },
  async members(workspaceId: string): Promise<WorkspaceMemberDTO[]> {
    const res = await api.get<ApiEnvelope<WorkspaceMemberDTO[]>>(
      `/workspaces/${encodeURIComponent(workspaceId)}/members`,
    );
    return unwrap(res);
  },
  async access(workspaceId: string): Promise<WorkspaceAccessDTO> {
    const res = await api.get<ApiEnvelope<WorkspaceAccessDTO>>(
      "/workspaces/current/access",
      { params: { workspace_id: workspaceId } },
    );
    return unwrap(res);
  },
  async resolveJoinCode(code: string): Promise<{ name: string }> {
    const res = await api.post<ApiEnvelope<{ name: string }>>(
      "/workspace-access/resolve-code",
      { code },
    );
    return unwrap(res);
  },
  async requestAccess(payload: { code: string; message?: string }): Promise<WorkspaceAccessRequestDTO> {
    const res = await api.post<ApiEnvelope<WorkspaceAccessRequestDTO>>(
      "/workspace-access/requests",
      payload,
    );
    return unwrap(res);
  },
  async myAccessRequests(): Promise<WorkspaceAccessRequestDTO[]> {
    const res = await api.get<ApiEnvelope<WorkspaceAccessRequestDTO[]>>(
      "/workspace-access/my-requests",
    );
    return unwrap(res);
  },
  async accessRequests(workspaceId: string): Promise<WorkspaceAccessRequestDTO[]> {
    const res = await api.get<ApiEnvelope<WorkspaceAccessRequestDTO[]>>(
      `/workspaces/${encodeURIComponent(workspaceId)}/access-requests`,
    );
    return unwrap(res);
  },
  async approveAccessRequest(
    workspaceId: string,
    requestId: string,
    payload: { role: "admin" | "member"; capabilities: string[] },
  ): Promise<WorkspaceMemberDTO> {
    const res = await api.post<ApiEnvelope<WorkspaceMemberDTO>>(
      `/workspaces/${encodeURIComponent(workspaceId)}/access-requests/${encodeURIComponent(requestId)}/approve`,
      payload,
    );
    return unwrap(res);
  },
  async rejectAccessRequest(workspaceId: string, requestId: string, reason?: string): Promise<WorkspaceAccessRequestDTO> {
    const res = await api.post<ApiEnvelope<WorkspaceAccessRequestDTO>>(
      `/workspaces/${encodeURIComponent(workspaceId)}/access-requests/${encodeURIComponent(requestId)}/reject`,
      { reason },
    );
    return unwrap(res);
  },
  async joinSettings(workspaceId: string): Promise<WorkspaceJoinSettingsDTO> {
    const res = await api.get<ApiEnvelope<WorkspaceJoinSettingsDTO>>(
      `/workspaces/${encodeURIComponent(workspaceId)}/join-settings`,
    );
    return unwrap(res);
  },
  async regenerateJoinCode(workspaceId: string): Promise<WorkspaceJoinSettingsDTO> {
    const res = await api.post<ApiEnvelope<WorkspaceJoinSettingsDTO>>(
      `/workspaces/${encodeURIComponent(workspaceId)}/join-code/regenerate`,
    );
    return unwrap(res);
  },
  async setJoinEnabled(workspaceId: string, joinEnabled: boolean): Promise<WorkspaceJoinSettingsDTO> {
    const res = await api.patch<ApiEnvelope<WorkspaceJoinSettingsDTO>>(
      `/workspaces/${encodeURIComponent(workspaceId)}/join-settings`,
      { join_enabled: joinEnabled },
    );
    return unwrap(res);
  },
  async updateMemberCapabilities(workspaceId: string, membershipId: string, capabilities: string[]): Promise<{ capabilities: string[] }> {
    const res = await api.put<ApiEnvelope<{ capabilities: string[] }>>(
      `/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(membershipId)}/capabilities`,
      { capabilities },
    );
    return unwrap(res);
  },
  async updateMemberRole(
    workspaceId: string,
    membershipId: string,
    role: "admin" | "member",
  ): Promise<WorkspaceMemberDTO> {
    const res = await api.patch<ApiEnvelope<WorkspaceMemberDTO>>(
      `/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(membershipId)}`,
      { role },
    );
    return unwrap(res);
  },
  async removeMember(workspaceId: string, membershipId: string): Promise<void> {
    await api.delete(
      `/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(membershipId)}`,
    );
  },
};
