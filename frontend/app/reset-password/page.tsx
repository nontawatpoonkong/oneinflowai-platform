import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AuthLink, AuthShell } from "@/components/auth/auth-shell";
import { ResetPasswordForm } from "@/components/auth/reset-password-form";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("auth.resetPassword");
  return { title: t("title") };
}

export default async function ResetPasswordPage() {
  const t = await getTranslations("auth.resetPassword");
  return (
    <AuthShell
      title={t("title")}
      subtitle={t("subtitle")}
      footer={<AuthLink href="/login">{t("backToLogin")}</AuthLink>}
    >
      <ResetPasswordForm />
    </AuthShell>
  );
}
