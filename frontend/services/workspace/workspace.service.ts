import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope, WorkspaceDTO, WorkspaceMemberDTO } from "@/types/api";

export const workspaceService = {
  async me(): Promise<WorkspaceDTO> {
    const res = await api.get<ApiEnvelope<WorkspaceDTO>>("/workspaces/me");
    return unwrap(res);
  },

  async list(): Promise<WorkspaceDTO[]> {
    const res = await api.get<ApiEnvelope<WorkspaceDTO[]>>("/workspaces");
    return unwrap(res);
  },
  async members(workspaceId: string): Promise<WorkspaceMemberDTO[]> {
    const res = await api.get<ApiEnvelope<WorkspaceMemberDTO[]>>(
      `/workspaces/${encodeURIComponent(workspaceId)}/members`,
    );
    return unwrap(res);
  },
};
