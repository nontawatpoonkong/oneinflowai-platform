"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FieldError, FormError } from "@/components/auth/form-error";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/services/api/errors";
import { saveRegistrationVerification } from "@/services/auth/verification-session";

export function RegisterForm() {
  const t = useTranslations("auth.register");
  const tv = useTranslations("validation");
  const { register: registerUser } = useAuth();
  const router = useRouter();

  const schema = z.object({
    full_name: z.string().trim().min(1, tv("nameRequired")).max(255),
    email: z.string().min(1, tv("emailRequired")).email(tv("emailInvalid")),
    password: z.string().min(8, tv("passwordMin")),
  });
  type Values = z.infer<typeof schema>;

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: "", email: "", password: "" },
  });

  async function onSubmit(values: Values) {
    try {
      const result = await registerUser(values);
      saveRegistrationVerification(result.user.email, result);
      router.replace("/verify-email");
    } catch (error) {
      setError("root", {
        message: error instanceof ApiError ? error.message : t("error"),
      });
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5" noValidate>
      <FormError message={errors.root?.message} />

      <div className="flex flex-col gap-2">
        <Label htmlFor="full_name">{t("fullName")}</Label>
        <Input
          id="full_name"
          autoComplete="name"
          placeholder={t("fullNamePlaceholder")}
          aria-invalid={!!errors.full_name}
          {...register("full_name")}
        />
        <FieldError message={errors.full_name?.message} />
      </div>

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
          autoComplete="new-password"
          placeholder={t("passwordPlaceholder")}
          aria-invalid={!!errors.password}
          {...register("password")}
        />
        <FieldError message={errors.password?.message} />
      </div>

      <Button type="submit" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? <Loader2 className="size-4 animate-spin" /> : null}
        {t("submit")}
      </Button>
    </form>
  );
}
