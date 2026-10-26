import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type {
  PMSConnection,
  PMSConnectionCreate,
  PMSInventoryAuthority,
  PMSMapping,
  PMSMappingCreate,
  PMSProviderSummary,
  PMSReconciliationIssue,
  PMSSyncRun,
} from "@/types/pms";

export const pmsService = {
  async providers(): Promise<PMSProviderSummary[]> {
    return unwrap(
      await api.get<ApiEnvelope<PMSProviderSummary[]>>("/pms/providers"),
    );
  },
  async connections(): Promise<PMSConnection[]> {
    return unwrap(
      await api.get<ApiEnvelope<PMSConnection[]>>("/pms/connections"),
    );
  },
  async createConnection(payload: PMSConnectionCreate): Promise<PMSConnection> {
    return unwrap(
      await api.post<ApiEnvelope<PMSConnection>>("/pms/connections", payload),
    );
  },
  async updateConnection(
    id: string,
    payload: { active?: boolean; inventory_authority?: PMSInventoryAuthority },
  ): Promise<PMSConnection> {
    return unwrap(
      await api.patch<ApiEnvelope<PMSConnection>>(
        `/pms/connections/${encodeURIComponent(id)}`,
        payload,
      ),
    );
  },
  async testConnection(id: string): Promise<PMSConnection> {
    return unwrap(
      await api.post<ApiEnvelope<PMSConnection>>(
        `/pms/connections/${encodeURIComponent(id)}/test`,
      ),
    );
  },
  async sync(id: string): Promise<PMSSyncRun> {
    return unwrap(
      await api.post<ApiEnvelope<PMSSyncRun>>(
        `/pms/connections/${encodeURIComponent(id)}/sync`,
      ),
    );
  },
  async mappings(connectionId?: string): Promise<PMSMapping[]> {
    return unwrap(
      await api.get<ApiEnvelope<PMSMapping[]>>("/pms/mappings", {
        params: { connection_id: connectionId },
      }),
    );
  },
  async createMapping(payload: PMSMappingCreate): Promise<PMSMapping> {
    return unwrap(
      await api.post<ApiEnvelope<PMSMapping>>("/pms/mappings", payload),
    );
  },
  async syncRuns(connectionId?: string): Promise<PMSSyncRun[]> {
    return unwrap(
      await api.get<ApiEnvelope<PMSSyncRun[]>>("/pms/sync-runs", {
        params: { connection_id: connectionId },
      }),
    );
  },
  async issues(connectionId?: string): Promise<PMSReconciliationIssue[]> {
    return unwrap(
      await api.get<ApiEnvelope<PMSReconciliationIssue[]>>(
        "/pms/reconciliation/issues",
        { params: { connection_id: connectionId } },
      ),
    );
  },
};
