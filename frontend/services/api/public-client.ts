import axios, { type AxiosResponse } from "axios";

import { normalizeError } from "@/services/api/errors";
import type { ApiEnvelope } from "@/types/api";

const configuredBaseUrl = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const normalizedBaseUrl = configuredBaseUrl.replace(/\/+$/, "");
const baseURL = normalizedBaseUrl.endsWith("/api/v1")
  ? normalizedBaseUrl
  : `${normalizedBaseUrl}/api/v1`;

export const publicApi = axios.create({
  baseURL,
  timeout: 15000,
  headers: { "Content-Type": "application/json" },
});

publicApi.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(normalizeError(error)),
);

export function unwrapPublic<T>(response: AxiosResponse<ApiEnvelope<T>>): T {
  return response.data.data;
}
