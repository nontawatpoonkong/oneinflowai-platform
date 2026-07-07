"use client";

import { motion, useScroll, useTransform } from "framer-motion";
import { ArrowRight, PlayCircle } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useRef } from "react";

import { AINetworkBackground } from "@/components/shared/ai-network-background";
import { ConversationPreview } from "@/components/landing/conversation-preview";
import { Magnetic } from "@/components/shared/magnetic";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fadeUp, staggerContainer } from "@/lib/animations";

export function Hero() {
  const t = useTranslations("landing.hero");
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const y = useTransform(scrollYProgress, [0, 1], [0, -60]);
  const opacity = useTransform(scrollYProgress, [0, 0.8], [1, 0]);

  return (
    <section ref={ref} className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 -z-10 opacity-70">
        <AINetworkBackground />
      </div>
      <div className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[460px] w-[880px] -translate-x-1/2 rounded-full bg-brand/20 blur-[150px]" />

      <motion.div
        style={{ y, opacity }}
        className="container-wide grid items-center gap-14 pb-24 pt-20 md:pt-28 lg:grid-cols-[1.05fr_0.95fr]"
      >
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="flex flex-col items-start gap-6 text-left"
        >
          <motion.div variants={fadeUp}>
            <Badge>
              <span className="size-1.5 rounded-full bg-brand" />
              {t("badge")}
            </Badge>
          </motion.div>

          <motion.h1
            variants={fadeUp}
            className="text-balance text-4xl font-semibold leading-[1.1] tracking-tight sm:text-6xl md:text-7xl"
          >
            {t("headline1")}
            <br />
            {t("headline2")}
            <br />
            <span className="text-gradient">{t("headline3")}</span>
          </motion.h1>

          <motion.p
            variants={fadeUp}
            className="max-w-xl text-pretty text-base text-muted-foreground sm:text-lg"
          >
            {t("subtitle")}
          </motion.p>

          <motion.div
            variants={fadeUp}
            className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center"
          >
            <Magnetic>
              <Button asChild size="lg">
                <Link href="/dashboard">
                  {t("primaryCta")} <ArrowRight className="size-4" />
                </Link>
              </Button>
            </Magnetic>
            <Magnetic>
              <Button asChild size="lg" variant="glass">
                <Link href="#roi">
                  <PlayCircle className="size-4" /> {t("secondaryCta")}
                </Link>
              </Button>
            </Magnetic>
          </motion.div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 30, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ type: "spring", stiffness: 90, damping: 16, delay: 0.2 }}
          className="flex justify-center lg:justify-end"
        >
          <ConversationPreview />
        </motion.div>
      </motion.div>
    </section>
  );
}
