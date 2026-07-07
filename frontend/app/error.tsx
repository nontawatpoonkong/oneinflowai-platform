"use client";

import { RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("errors");
  const tc = useTranslations("common");

  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error(error);
  }, [error]);

  return (
    <div className="grid min-h-dvh place-items-center px-6">
      <div className="flex flex-col items-center gap-6 text-center">
        <p className="text-6xl font-semibold tracking-tight text-gradient">500</p>
        <div>
          <h1 className="text-xl font-semibold">{t("serverTitle")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("serverDesc")}</p>
        </div>
        <Button onClick={reset}>
          <RefreshCw className="size-4" /> {tc("tryAgain")}
        </Button>
      </div>
    </div>
  );
}
