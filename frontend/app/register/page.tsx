import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AuthLink, AuthShell } from "@/components/auth/auth-shell";
import { RegisterForm } from "@/components/auth/register-form";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("register") };
}

export default async function RegisterPage() {
  const t = await getTranslations("auth.register");
  return (
    <AuthShell
      title={t("title")}
      subtitle={t("subtitle")}
      footer={
        <>
          {t("footerText")} <AuthLink href="/login">{t("footerLink")}</AuthLink>
        </>
      }
    >
      <RegisterForm />
    </AuthShell>
  );
}
