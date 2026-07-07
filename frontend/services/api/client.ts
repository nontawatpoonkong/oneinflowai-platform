import axios, { type AxiosResponse } from "axios";

import { clearToken, getToken } from "@/services/auth/token";
import { normalizeError } from "@/services/api/errors";
import type { ApiEnvelope } from "@/types/api";

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "/api/v1",
  timeout: 15000,
  headers: { "Content-Type": "application/json" },
});

// Attach the bearer token to every request.
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
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
