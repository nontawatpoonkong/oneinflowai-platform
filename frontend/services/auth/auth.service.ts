import { api, unwrap } from "@/services/api/client";
import type {
  ApiEnvelope,
  LoginPayload,
  RegisterPayload,
  RegisterResultDTO,
  ResendVerificationResultDTO,
  TokenDTO,
  UserDTO,
  VerifyEmailPayload,
} from "@/types/api";

export const authService = {
  async login(payload: LoginPayload): Promise<TokenDTO> {
    const res = await api.post<ApiEnvelope<TokenDTO>>("/auth/login", {
      email: payload.email,
      password: payload.password,
    });
    return unwrap(res);
  },

  async register(payload: RegisterPayload): Promise<RegisterResultDTO> {
    const res = await api.post<ApiEnvelope<RegisterResultDTO>>(
      "/auth/register",
      payload,
    );
    return unwrap(res);
  },

  async verifyEmail(payload: VerifyEmailPayload): Promise<void> {
    await api.post<ApiEnvelope<null>>("/auth/verify-email", payload);
  },

  async resendVerification(
    email: string,
  ): Promise<ResendVerificationResultDTO> {
    const res = await api.post<ApiEnvelope<ResendVerificationResultDTO>>(
      "/auth/resend-verification",
      { email },
    );
    return unwrap(res);
  },

  async me(): Promise<UserDTO> {
    const res = await api.get<ApiEnvelope<UserDTO>>("/auth/me");
    return unwrap(res);
  },
};
