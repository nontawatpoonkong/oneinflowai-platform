"use client";

import { ArrowRight, CheckCircle2, Workflow } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { ConversationPreview } from "@/components/landing/conversation-preview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function Hero() {
  const t = useTranslations("landing.hero");
  const reduceMotion = useReducedMotion();

  const entrance = {
    hidden: { opacity: 0, y: 18 },
    visible: { opacity: 1, y: 0 },
  };

  return (
    <section className="relative overflow-hidden border-b border-border bg-[linear-gradient(180deg,hsl(var(--brand)/0.08),hsl(var(--background))_55%)]">
      <div aria-hidden className="absolute inset-0 bg-dotgrid opacity-60 [mask-image:linear-gradient(to_bottom,black,transparent_75%)]" />
      <div aria-hidden className="absolute inset-x-0 top-0 h-1 overflow-hidden bg-[linear-gradient(90deg,hsl(var(--brand))_0_70%,hsl(var(--brand-secondary))_70%_100%)]">
        <motion.span
          className="absolute inset-y-0 w-32 bg-white/70 blur-md"
          animate={reduceMotion ? undefined : { x: ["-20vw", "110vw"] }}
          transition={{ duration: 4.8, ease: "linear", repeat: Infinity, repeatDelay: 1.2 }}
        />
      </div>
      <motion.div
        aria-hidden
        className="absolute left-[8%] top-28 size-48 rounded-full bg-brand/14 blur-3xl sm:size-72"
        animate={reduceMotion ? undefined : { x: [0, 36, -8, 0], y: [0, -18, 22, 0], scale: [1, 1.12, 0.96, 1] }}
        transition={{ duration: 14, ease: "easeInOut", repeat: Infinity }}
      />
      <motion.div
        aria-hidden
        className="absolute right-[5%] top-40 size-44 rounded-full border border-brand-secondary/30 bg-brand-secondary/10 blur-3xl sm:size-64"
        animate={reduceMotion ? undefined : { x: [0, -28, 14, 0], y: [0, 22, -14, 0], scale: [1, 0.92, 1.08, 1] }}
        transition={{ duration: 17, ease: "easeInOut", repeat: Infinity }}
      />
      <div aria-hidden className="absolute left-1/2 top-20 h-56 w-[70%] -translate-x-1/2 rounded-full border border-brand-secondary/20 bg-brand/5 blur-3xl" />
      <div className="container-wide relative z-10 flex flex-col items-center py-14 text-center sm:py-20 lg:py-24">
        <motion.div
          className="flex max-w-4xl flex-col items-center gap-6"
          initial="hidden"
          animate="visible"
          variants={{ visible: { transition: { staggerChildren: 0.11, delayChildren: 0.08 } } }}
        >
          <motion.div variants={entrance}>
            <Badge variant="outline" className="rounded-md border-brand/30 bg-brand-soft text-foreground shadow-[0_0_24px_hsl(var(--brand)/0.12)]">
            <Workflow className="size-3.5 text-brand" />
            {t("badge")}
            </Badge>
          </motion.div>

          <motion.h1 variants={entrance} className="text-balance text-4xl font-semibold leading-[1.1] tracking-[-0.04em] sm:text-5xl lg:text-[4rem]">
            {t("headline1")}
            <br />
            <span className="text-brand">{t("headline2")}</span>
            <span className="ml-1 inline-block border-b-2 border-brand-secondary pb-1 text-foreground">{t("headlineAccent")}</span>
          </motion.h1>

          <motion.p variants={entrance} className="max-w-3xl text-pretty text-base leading-7 text-muted-foreground sm:text-lg">
            {t("subtitle")}
          </motion.p>

          <motion.div variants={entrance} className="flex w-full flex-col justify-center gap-3 sm:w-auto sm:flex-row">
            <Button asChild size="lg" className="group shadow-[0_10px_35px_hsl(var(--brand)/0.22)] transition-transform hover:-translate-y-0.5">
              <Link href="/register">{t("primaryCta")} <ArrowRight className="size-4" /></Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="border-brand-secondary/60 bg-card text-foreground transition-transform hover:-translate-y-0.5 hover:border-brand-secondary hover:bg-card hover:text-foreground">
              <Link href="#workflow">{t("secondaryCta")}</Link>
            </Button>
          </motion.div>

          <motion.p variants={entrance} className="flex max-w-xl items-start gap-2 text-left text-sm leading-6 text-muted-foreground sm:text-center">
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand" />
            {t("trustLine")}
          </motion.p>
        </motion.div>

        <motion.div
          className="mt-12 w-full"
          initial={{ opacity: 0, y: 36, scale: 0.985 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ delay: 0.65, duration: 0.8 }}
        >
          <ConversationPreview />
        </motion.div>
      </div>
    </section>
  );
}
