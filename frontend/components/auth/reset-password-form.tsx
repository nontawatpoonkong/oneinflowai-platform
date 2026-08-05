"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
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
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { FieldError, FormError } from "@/components/auth/form-error";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/services/api/errors";
import { authService } from "@/services/auth/auth.service";
import {
  clearPasswordResetSession,
  readPasswordResetSession,
  savePasswordResetSession,
  type PasswordResetSession,
} from "@/services/auth/password-reset-session";

export function ResetPasswordForm() {
  const t = useTranslations("auth.resetPassword");
  const tv = useTranslations("validation");
  const router = useRouter();
  const [session, setSession] = useState<PasswordResetSession | null>(null);
  const [ready, setReady] = useState(false);
  const [otp, setOtp] = useState("");
  const [resetToken, setResetToken] = useState<string>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    const stored = readPasswordResetSession();
    setSession(stored);
    setReady(true);
    const update = () => {
      const current = readPasswordResetSession();
      setRemaining(
        current
          ? Math.max(0, Math.ceil((current.resendAvailableAt - Date.now()) / 1000))
          : 0,
      );
    };
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const passwordSchema = z
    .object({
      new_password: z.string().min(8, tv("passwordMin")).max(128),
      confirm_password: z.string().min(1, tv("passwordRequired")),
    })
    .refine((value) => value.new_password === value.confirm_password, {
      path: ["confirm_password"],
      message: t("passwordMismatch"),
    });
  type PasswordValues = z.infer<typeof passwordSchema>;
  const form = useForm<PasswordValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { new_password: "", confirm_password: "" },
  });

  function updateOtp(value: string) {
    setOtp(value.replace(/[^0-9]/g, "").slice(0, 6));
    setError(undefined);
  }

  async function verifyOtp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session || otp.length !== 6) return;
    setBusy(true);
    setError(undefined);
    try {
      const result = await authService.verifyPasswordReset({
        email: session.email,
        otp,
      });
      setOtp("");
      setResetToken(result.reset_token);
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.code === "INVALID_PASSWORD_RESET_CODE"
          ? t("invalidCode")
          : t("error"),
      );
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    if (!session || remaining > 0) return;
    setBusy(true);
    try {
      const result = await authService.forgotPassword(session.email);
      savePasswordResetSession(session.email, result.resend_after);
      const updated = readPasswordResetSession();
      setSession(updated);
      setRemaining(result.resend_after);
      toast.success(t("resendSuccess"));
    } catch {
      setError(t("error"));
    } finally {
      setBusy(false);
    }
  }

  async function submitPassword(values: PasswordValues) {
    if (!resetToken) return;
    try {
      await authService.resetPassword({ reset_token: resetToken, ...values });
      clearPasswordResetSession();
      toast.success(t("success"));
      router.replace("/login?passwordReset=1");
    } catch (caught) {
      form.setError("root", {
        message: caught instanceof ApiError ? caught.message : t("error"),
      });
    }
  }

  if (!ready) return <Loader2 className="mx-auto size-5 animate-spin" />;
  if (!session) {
    return (
      <div className="flex flex-col gap-4 text-center">
        <FormError message={t("missingSession")} />
        <Button asChild variant="outline"><Link href="/forgot-password">{t("startAgain")}</Link></Button>
      </div>
    );
  }

  if (!resetToken) {
    return (
      <form
        key="otp-step"
        onSubmit={verifyOtp}
        className="flex flex-col gap-5"
        noValidate
      >
        <FormError message={error} />
        <div className="flex flex-col gap-2">
          <Label htmlFor="reset-code">{t("codeLabel")}</Label>
          <Input
            id="reset-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength={6}
            value={otp}
            onChange={(event: ChangeEvent<HTMLInputElement>) => updateOtp(event.target.value)}
            onPaste={(event: ClipboardEvent<HTMLInputElement>) => {
              event.preventDefault();
              updateOtp(event.clipboardData.getData("text"));
            }}
            className="h-14 text-center font-mono text-2xl tracking-[0.45em]"
            autoFocus
          />
        </div>
        <Button type="submit" disabled={busy || otp.length !== 6}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : null}{t("verify")}
        </Button>
        {remaining > 0 ? (
          <p className="text-center text-sm text-muted-foreground">{t("countdown", { seconds: remaining })}</p>
        ) : (
          <Button type="button" variant="link" onClick={resend} disabled={busy}>{t("resend")}</Button>
        )}
      </form>
    );
  }

  return (
    <form
      key="password-step"
      onSubmit={form.handleSubmit(submitPassword)}
      className="flex flex-col gap-5"
      noValidate
    >
      <FormError message={form.formState.errors.root?.message} />
      <div className="flex flex-col gap-2">
        <Label htmlFor="new_password">{t("newPassword")}</Label>
        <Input id="new_password" type="password" autoComplete="new-password" {...form.register("new_password")} />
        <FieldError message={form.formState.errors.new_password?.message} />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="confirm_password">{t("confirmPassword")}</Label>
        <Input id="confirm_password" type="password" autoComplete="new-password" {...form.register("confirm_password")} />
        <FieldError message={form.formState.errors.confirm_password?.message} />
      </div>
      <Button type="submit" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? <Loader2 className="size-4 animate-spin" /> : null}{t("submit")}
      </Button>
    </form>
  );
}
