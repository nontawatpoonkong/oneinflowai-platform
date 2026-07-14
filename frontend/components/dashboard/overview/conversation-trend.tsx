"use client";

import { motion } from "framer-motion";
import { LineChart } from "lucide-react";
import { useTranslations } from "next-intl";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fadeUp, VIEWPORT } from "@/lib/animations";

export function ConversationTrend() {
  const t = useTranslations("dashboard.owner.trend");

  return (
    <motion.div
      variants={fadeUp}
      initial="hidden"
      whileInView="visible"
      viewport={VIEWPORT}
    >
      <Card>
        <CardHeader>
          <CardTitle>{t("title")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-80 flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-border bg-muted/20 text-center">
            <span className="grid size-14 place-items-center rounded-2xl bg-brand/10 text-brand">
              <LineChart className="size-7" />
            </span>
            <p className="text-sm font-medium text-muted-foreground">
              {t("comingSoon")}
            </p>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
