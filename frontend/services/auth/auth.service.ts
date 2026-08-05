import { api, unwrap } from "@/services/api/client";
import type {
  ApiEnvelope,
  ForgotPasswordResultDTO,
  LoginPayload,
  RegisterPayload,
  RegisterResultDTO,
  ResetPasswordPayload,
  ResendVerificationResultDTO,
  TokenDTO,
  UserDTO,
  VerifyEmailPayload,
  VerifyPasswordResetPayload,
  VerifyPasswordResetResultDTO,
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

  async forgotPassword(email: string): Promise<ForgotPasswordResultDTO> {
    const res = await api.post<ApiEnvelope<ForgotPasswordResultDTO>>(
      "/auth/forgot-password",
      { email },
    );
    return unwrap(res);
  },

  async verifyPasswordReset(
    payload: VerifyPasswordResetPayload,
  ): Promise<VerifyPasswordResetResultDTO> {
    const res = await api.post<ApiEnvelope<VerifyPasswordResetResultDTO>>(
      "/auth/verify-password-reset",
      payload,
    );
    return unwrap(res);
  },

  async resetPassword(payload: ResetPasswordPayload): Promise<void> {
    await api.post<ApiEnvelope<null>>("/auth/reset-password", payload);
  },

  async me(): Promise<UserDTO> {
    const res = await api.get<ApiEnvelope<UserDTO>>("/auth/me");
    return unwrap(res);
  },
};
