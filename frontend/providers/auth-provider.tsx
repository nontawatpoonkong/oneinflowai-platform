"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { queryKeys } from "@/lib/query-keys";
import { authService } from "@/services/auth/auth.service";
import { clearToken, getToken, setToken } from "@/services/auth/token";
import type {
  LoginPayload,
  RegisterPayload,
  RegisterResultDTO,
  UserDTO,
} from "@/types/api";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  user: UserDTO | null;
  status: AuthStatus;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<RegisterResultDTO>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [hasToken, setHasToken] = useState<boolean>(() => !!getToken());

  const meQuery = useQuery({
    queryKey: queryKeys.me,
    queryFn: authService.me,
    enabled: hasToken,
    retry: false,
    staleTime: 5 * 60_000,
  });

  // Invalid/expired token -> drop it so guards treat the user as guest.
  useEffect(() => {
    if (hasToken && meQuery.isError) {
      clearToken();
      setHasToken(false);
    }
  }, [hasToken, meQuery.isError]);

  const loginMutation = useMutation({
    mutationFn: (payload: LoginPayload) => authService.login(payload),
    onSuccess: (token, variables) => {
      setToken(token.access_token, variables.remember);
      setHasToken(true);
    },
  });

  const registerMutation = useMutation({
    mutationFn: (payload: RegisterPayload) => authService.register(payload),
  });

  const login = useCallback(
    async (payload: LoginPayload) => {
      await loginMutation.mutateAsync(payload);
      await queryClient.invalidateQueries({ queryKey: queryKeys.me });
    },
    [loginMutation, queryClient],
  );

  const register = useCallback(
    async (payload: RegisterPayload) => {
      return registerMutation.mutateAsync(payload);
    },
    [registerMutation],
  );

  const logout = useCallback(() => {
    clearToken();
    setHasToken(false);
    queryClient.clear();
    router.replace("/login");
  }, [queryClient, router]);

  const status: AuthStatus = !hasToken
    ? "unauthenticated"
    : meQuery.data
      ? "authenticated"
      : meQuery.isError
        ? "unauthenticated"
        : "loading";

  const value = useMemo<AuthContextValue>(
    () => ({ user: meQuery.data ?? null, status, login, register, logout }),
    [meQuery.data, status, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
