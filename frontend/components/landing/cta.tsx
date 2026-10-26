"use client";

import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { scaleIn, VIEWPORT } from "@/lib/animations";

export function Cta() {
  const t = useTranslations("landing.cta");

  return (
    <section className="container-wide py-24">
      <motion.div
        variants={scaleIn}
        initial="hidden"
        whileInView="visible"
        viewport={VIEWPORT}
        className="rounded-xl border border-border bg-foreground px-8 py-14 text-center text-background"
      >
        <div className="mx-auto flex max-w-2xl flex-col items-center gap-5">
          <h2 className="text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
            {t("title")}
          </h2>
          <p className="text-background/70">{t("description")}</p>
          <div className="flex w-full flex-col justify-center gap-3 sm:w-auto sm:flex-row">
            <Button asChild size="lg">
              <Link href="/register">
                {t("button")} <ArrowRight className="size-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="border-brand-secondary/60 bg-transparent text-background hover:bg-brand-secondary hover:text-white">
              <Link href="#workflow">{t("secondaryButton")}</Link>
            </Button>
          </div>
        </div>
      </motion.div>
    </section>
  );
}
