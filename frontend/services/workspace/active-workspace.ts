const ACTIVE_WORKSPACE_KEY = "oneinflow_active_workspace_id";

export function getActiveWorkspaceId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACTIVE_WORKSPACE_KEY);
}

export function setActiveWorkspaceId(workspaceId: string): void {
  window.localStorage.setItem(ACTIVE_WORKSPACE_KEY, workspaceId);
}

export function clearActiveWorkspaceId(): void {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(ACTIVE_WORKSPACE_KEY);
  }
}
