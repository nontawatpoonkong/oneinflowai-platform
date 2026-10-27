import axios, { type AxiosResponse } from "axios";

import { clearToken, getToken } from "@/services/auth/token";
import { getActiveWorkspaceId } from "@/services/workspace/active-workspace";
import { normalizeError } from "@/services/api/errors";
import type { ApiEnvelope } from "@/types/api";

// The backend serves every endpoint under /api/v1. Guarantee that prefix is
// present so requests become http://localhost:8000/api/v1/... and never hit
// http://localhost:8000/auth/... directly. Defaults to the same-origin proxy.
const configuredBaseUrl = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const normalizedBaseUrl = configuredBaseUrl.replace(/\/+$/, "");
const baseURL = normalizedBaseUrl.endsWith("/api/v1")
  ? normalizedBaseUrl
  : `${normalizedBaseUrl}/api/v1`;

export const api = axios.create({
  baseURL,
  timeout: 15000,
  headers: { "Content-Type": "application/json" },
});

// Attach the bearer token to every request.
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  const workspaceId = getActiveWorkspaceId();
  if (workspaceId) config.headers["X-Workspace-ID"] = workspaceId;
  return config;
});

// Clear the token on expiry / auth failure; normalize all errors.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      clearToken();
    }
    return Promise.reject(normalizeError(error));
  },
);

/** Unwrap the standard { success, data, ... } envelope. */
export function unwrap<T>(response: AxiosResponse<ApiEnvelope<T>>): T {
  return response.data.data;
}
