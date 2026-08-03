import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AuthLink, AuthShell } from "@/components/auth/auth-shell";
import { EmailVerificationForm } from "@/components/auth/email-verification-form";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("verifyEmail") };
}

export default async function VerifyEmailPage() {
  const t = await getTranslations("auth.verifyEmail");
  return (
    <AuthShell
      title={t("title")}
      subtitle={t("subtitle")}
      footer={
        <>
          {t("footerText")} <AuthLink href="/login">{t("backToLogin")}</AuthLink>
        </>
      }
    >
      <EmailVerificationForm />
    </AuthShell>
  );
}
