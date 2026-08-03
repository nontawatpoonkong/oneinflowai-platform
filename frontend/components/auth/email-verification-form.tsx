"use client";

import { Loader2, Mail } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import {
  type ChangeEvent,
  type ClipboardEvent,
  type FormEvent,
  useEffect,
  useState,
} from "react";
import { toast } from "sonner";

import { FormError } from "@/components/auth/form-error";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/services/api/errors";
import { authService } from "@/services/auth/auth.service";
import {
  maskEmail,
  readVerificationSession,
  setResendCooldown,
  type VerificationSession,
} from "@/services/auth/verification-session";

export function EmailVerificationForm() {
  const t = useTranslations("auth.verifyEmail");
  const router = useRouter();
  const [session, setSession] = useState<VerificationSession | null>(null);
  const [ready, setReady] = useState(false);
  const [otp, setOtp] = useState("");
  const [error, setError] = useState<string>();
  const [isVerifying, setIsVerifying] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    const pending = readVerificationSession();
    setSession(pending);
    setReady(true);
    if (!pending) return;

    const updateRemaining = () => {
      const latest = readVerificationSession();
      if (!latest) {
        setRemaining(0);
        return;
      }
      setRemaining(
        Math.max(0, Math.ceil((latest.resendAvailableAt - Date.now()) / 1000)),
      );
    };
    updateRemaining();
    const timer = window.setInterval(updateRemaining, 1000);
    return () => window.clearInterval(timer);
  }, []);

  function updateOtp(value: string) {
    setOtp(value.replace(/[^0-9]/g, "").slice(0, 6));
    setError(undefined);
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    updateOtp(event.target.value);
  }

  function handlePaste(event: ClipboardEvent<HTMLInputElement>) {
    const pasted = event.clipboardData.getData("text");
    const digits = pasted.replace(/[^0-9]/g, "").slice(0, 6);
    if (!digits) return;
    event.preventDefault();
    updateOtp(digits);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;
    if (otp.length !== 6) {
      setError(t("codeLength"));
      return;
    }

    setIsVerifying(true);
    setError(undefined);
    try {
      await authService.verifyEmail({ email: session.email, otp });
      setOtp("");
      toast.success(t("verified"));
      router.replace("/login?verified=1");
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.code === "INVALID_VERIFICATION_CODE"
          ? t("invalidCode")
          : t("verifyError"),
      );
    } finally {
      setIsVerifying(false);
    }
  }

  async function handleResend() {
    if (!session || remaining > 0) return;
    setIsResending(true);
    setError(undefined);
    try {
      const result = await authService.resendVerification(session.email);
      setResendCooldown(result.resend_after);
      const updated = readVerificationSession();
      setSession(updated);
      setRemaining(result.resend_after);
      toast.success(t("resendSuccess"));
    } catch {
      setError(t("resendError"));
    } finally {
      setIsResending(false);
    }
  }

  if (!ready) {
    return (
      <div className="flex justify-center py-8" aria-label={t("loading")}>
        <Loader2 className="size-5 animate-spin text-brand" />
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex flex-col gap-4 text-center">
        <FormError message={t("missingEmail")} />
        <Button asChild variant="outline">
          <Link href="/login">{t("backToLogin")}</Link>
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
      <div className="flex items-center justify-center gap-2 rounded-xl border border-border bg-muted/40 px-4 py-3 text-sm">
        <Mail className="size-4 shrink-0 text-brand" />
        <span>{maskEmail(session.email)}</span>
      </div>

      <FormError message={error} />

      <div className="flex flex-col gap-2">
        <label htmlFor="verification-code" className="text-sm font-medium">
          {t("codeLabel")}
        </label>
        <Input
          id="verification-code"
          name="verification-code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]{6}"
          maxLength={6}
          value={otp}
          onChange={handleChange}
          onPaste={handlePaste}
          aria-invalid={!!error}
          aria-describedby="verification-code-hint"
          className="h-14 text-center font-mono text-2xl tracking-[0.45em]"
          placeholder="000000"
          autoFocus
        />
        <p id="verification-code-hint" className="text-xs text-muted-foreground">
          {t("codeHint")}
        </p>
      </div>

      <Button
        type="submit"
        className="w-full"
        disabled={isVerifying || otp.length !== 6}
      >
        {isVerifying ? <Loader2 className="size-4 animate-spin" /> : null}
        {t("submit")}
      </Button>

      <div className="text-center text-sm text-muted-foreground">
        {remaining > 0 ? (
          <p>{t("resendCountdown", { seconds: remaining })}</p>
        ) : (
          <Button
            type="button"
            variant="link"
            className="h-auto p-0"
            disabled={isResending}
            onClick={handleResend}
          >
            {isResending ? <Loader2 className="size-4 animate-spin" /> : null}
            {t("resend")}
          </Button>
        )}
      </div>
    </form>
  );
}
