import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { Logo } from "@/components/shared/logo";
import { Button } from "@/components/ui/button";

export default async function NotFound() {
  const t = await getTranslations("errors");
  const tc = await getTranslations("common");

  return (
    <div className="relative grid min-h-dvh place-items-center overflow-hidden px-6">
      <div className="pointer-events-none absolute left-1/2 top-1/3 -z-10 h-72 w-[560px] -translate-x-1/2 rounded-full bg-brand/20 blur-[130px]" />
      <div className="flex flex-col items-center gap-6 text-center">
        <Logo />
        <p className="text-7xl font-semibold tracking-tight text-gradient">404</p>
        <div>
          <h1 className="text-xl font-semibold">{t("notFoundTitle")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("notFoundDesc")}</p>
        </div>
        <Button asChild>
          <Link href="/">{tc("backToHome")}</Link>
        </Button>
      </div>
    </div>
  );
}
