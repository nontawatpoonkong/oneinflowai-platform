const STORAGE_KEY = "oneflow_password_reset";

export interface PasswordResetSession {
  email: string;
  resendAvailableAt: number;
}

function storage(): Storage | null {
  return typeof window === "undefined" ? null : window.sessionStorage;
}

export function savePasswordResetSession(email: string, resendAfter: number): void {
  storage()?.setItem(
    STORAGE_KEY,
    JSON.stringify({
      email,
      resendAvailableAt: Date.now() + resendAfter * 1000,
    }),
  );
}

export function readPasswordResetSession(): PasswordResetSession | null {
  const raw = storage()?.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<PasswordResetSession>;
    if (
      typeof parsed.email !== "string" ||
      !parsed.email ||
      typeof parsed.resendAvailableAt !== "number"
    ) {
      return null;
    }
    return { email: parsed.email, resendAvailableAt: parsed.resendAvailableAt };
  } catch {
    storage()?.removeItem(STORAGE_KEY);
    return null;
  }
}

export function clearPasswordResetSession(): void {
  storage()?.removeItem(STORAGE_KEY);
}
