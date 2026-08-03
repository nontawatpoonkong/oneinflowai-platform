"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useForm } from "react-hook-form";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { FieldError, FormError } from "@/components/auth/form-error";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/services/api/errors";
import {
  clearVerificationSession,
  readVerificationSession,
  saveUnverifiedEmail,
} from "@/services/auth/verification-session";

export function LoginForm() {
  const t = useTranslations("auth.login");
  const tv = useTranslations("validation");
  const tToast = useTranslations("toasts");
  const { login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [verificationRequired, setVerificationRequired] = useState(false);

  const schema = z.object({
    email: z.string().min(1, tv("emailRequired")).email(tv("emailInvalid")),
    password: z.string().min(1, tv("passwordRequired")),
    remember: z.boolean(),
  });
  type Values = z.infer<typeof schema>;

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "", remember: false },
  });

  useEffect(() => {
    const pending = readVerificationSession();
    if (pending) setValue("email", pending.email);
  }, [setValue]);

  async function onSubmit(values: Values) {
    try {
      setVerificationRequired(false);
      await login(values);
      clearVerificationSession();
      toast.success(tToast("loginSuccess"));
      router.replace(params.get("next") ?? "/dashboard");
    } catch (error) {
      const needsVerification =
        error instanceof ApiError &&
        (error.code === "EMAIL_NOT_VERIFIED" ||
          (isRecord(error.details) &&
            error.details.next_action === "VERIFY_EMAIL"));
      if (needsVerification) {
        saveUnverifiedEmail(values.email);
        setVerificationRequired(true);
      }
      setError("root", {
        message: needsVerification
          ? t("emailNotVerified")
          : error instanceof ApiError
            ? error.message
            : t("error"),
      });
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5" noValidate>
      <FormError message={errors.root?.message} />
      {verificationRequired ? (
        <Button asChild type="button" variant="outline" className="w-full">
          <Link href="/verify-email">{t("verifyEmail")}</Link>
        </Button>
      ) : null}

      <div className="flex flex-col gap-2">
        <Label htmlFor="email">{t("email")}</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          placeholder="you@company.com"
          aria-invalid={!!errors.email}
          {...register("email")}
        />
        <FieldError message={errors.email?.message} />
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="password">{t("password")}</Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          placeholder="••••••••"
          aria-invalid={!!errors.password}
          {...register("password")}
        />
        <FieldError message={errors.password?.message} />
      </div>

      <div className="flex items-center justify-between">
        <Checkbox
          id="remember"
          label={t("remember")}
          checked={watch("remember")}
          onCheckedChange={(v) => setValue("remember", v)}
        />
        <a href="/forgot-password" className="text-sm font-medium text-brand hover:underline">
          {t("forgot")}
        </a>
      </div>

      <Button type="submit" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? <Loader2 className="size-4 animate-spin" /> : null}
        {t("submit")}
      </Button>
    </form>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
