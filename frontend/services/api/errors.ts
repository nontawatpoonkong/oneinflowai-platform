import axios from "axios";

import type { ApiEnvelope } from "@/types/api";

/** Normalized API error surfaced to the UI. */
export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(message: string, status = 0, code = "UNKNOWN", details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function normalizeError(error: unknown): ApiError {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status ?? 0;
    const envelope = error.response?.data as ApiEnvelope<unknown> | undefined;
    const message =
      envelope?.message ||
      (status === 0 ? "Unable to reach the server" : error.message);
    return new ApiError(
      message,
      status,
      envelope?.error?.code ?? "HTTP_ERROR",
      envelope?.error?.details,
    );
  }
  if (error instanceof Error) return new ApiError(error.message);
  return new ApiError("Unexpected error");
}
