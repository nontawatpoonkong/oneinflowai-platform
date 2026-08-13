import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope, WorkspaceAIInstructionsDTO, WorkspaceDTO, WorkspaceMemberDTO } from "@/types/api";

export const workspaceService = {
  async me(): Promise<WorkspaceDTO> {
    const res = await api.get<ApiEnvelope<WorkspaceDTO>>("/workspaces/me");
    return unwrap(res);
  },

  async list(): Promise<WorkspaceDTO[]> {
    const res = await api.get<ApiEnvelope<WorkspaceDTO[]>>("/workspaces");
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
};
