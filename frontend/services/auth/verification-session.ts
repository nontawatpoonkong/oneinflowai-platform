import type { RegisterResultDTO } from "@/types/api";

const STORAGE_KEY = "oneflow_email_verification";

export interface VerificationSession {
  email: string;
  expiresAt: number | null;
  resendAfter: number | null;
  resendAvailableAt: number;
}

function storage(): Storage | null {
  return typeof window === "undefined" ? null : window.sessionStorage;
}

export function readVerificationSession(): VerificationSession | null {
  const raw = storage()?.getItem(STORAGE_KEY);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as Partial<VerificationSession>;
    if (typeof parsed.email !== "string" || !parsed.email) return null;
    return {
      email: parsed.email,
      expiresAt: typeof parsed.expiresAt === "number" ? parsed.expiresAt : null,
      resendAfter:
        typeof parsed.resendAfter === "number" ? parsed.resendAfter : null,
      resendAvailableAt:
        typeof parsed.resendAvailableAt === "number"
          ? parsed.resendAvailableAt
          : Date.now(),
    };
  } catch {
    storage()?.removeItem(STORAGE_KEY);
    return null;
  }
}

export function saveRegistrationVerification(
  email: string,
  result: RegisterResultDTO,
): void {
  const now = Date.now();
  writeVerificationSession({
    email,
    expiresAt: now + result.verification_expires_in * 1000,
    resendAfter: result.resend_after,
    resendAvailableAt: now + result.resend_after * 1000,
  });
}

export function saveUnverifiedEmail(email: string): void {
  const current = readVerificationSession();
  if (current?.email.toLowerCase() === email.toLowerCase()) return;
  writeVerificationSession({
    email,
    expiresAt: null,
    resendAfter: null,
    resendAvailableAt: Date.now(),
  });
}

export function setResendCooldown(seconds: number): void {
  const current = readVerificationSession();
  if (!current) return;
  writeVerificationSession({
    ...current,
    resendAfter: seconds,
    resendAvailableAt: Date.now() + seconds * 1000,
  });
}

export function clearVerificationSession(): void {
  storage()?.removeItem(STORAGE_KEY);
}

export function maskEmail(email: string): string {
  const [local, domain] = email.split("@");
  if (!domain) return email;
  const visible = local.slice(0, Math.min(2, local.length));
  return `${visible}${"•".repeat(Math.max(3, local.length - visible.length))}@${domain}`;
}

function writeVerificationSession(value: VerificationSession): void {
  storage()?.setItem(STORAGE_KEY, JSON.stringify(value));
}
