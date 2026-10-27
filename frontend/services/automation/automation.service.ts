import { api, unwrap } from "@/services/api/client";
import type { ApiEnvelope } from "@/types/api";
import type {
  AutomationCreate,
  AutomationDefinition,
  AutomationExecution,
  AutomationExecutionList,
  AutomationList,
  AutomationOperationalStatus,
} from "@/types/automation";

export const automationService = {
  async list(): Promise<AutomationList> {
    return unwrap(
      await api.get<ApiEnvelope<AutomationList>>("/automations", {
        params: { page_size: 100 },
      }),
    );
  },
  async executions(): Promise<AutomationExecutionList> {
    return unwrap(
      await api.get<ApiEnvelope<AutomationExecutionList>>(
        "/automations/executions",
        { params: { page_size: 100 } },
      ),
    );
  },
  async create(payload: AutomationCreate): Promise<AutomationDefinition> {
    return unwrap(
      await api.post<ApiEnvelope<AutomationDefinition>>("/automations", payload),
    );
  },
  async status(): Promise<AutomationOperationalStatus> {
    return unwrap(
      await api.get<ApiEnvelope<AutomationOperationalStatus>>(
        "/automations/status",
      ),
    );
  },
  async retryExecution(id: string): Promise<AutomationExecution> {
    return unwrap(
      await api.post<ApiEnvelope<AutomationExecution>>(
        `/automations/executions/${id}/retry`,
      ),
    );
  },
  async enable(id: string): Promise<AutomationDefinition> {
    return unwrap(
      await api.post<ApiEnvelope<AutomationDefinition>>(
        `/automations/${id}/enable`,
      ),
    );
  },
  async disable(id: string): Promise<AutomationDefinition> {
    return unwrap(
      await api.post<ApiEnvelope<AutomationDefinition>>(
        `/automations/${id}/disable`,
      ),
    );
  },
};
