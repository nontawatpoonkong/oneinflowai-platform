"use client";

import { BedDouble, Bot, Check, CreditCard, MessageCircle, ShieldCheck } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslations } from "next-intl";

export function ConversationPreview() {
  const t = useTranslations("landing.hero.preview");
  const reduceMotion = useReducedMotion();
  const states = [
    { key: "availability", icon: BedDouble, tone: "cyan" },
    { key: "hold", icon: ShieldCheck, tone: "pink" },
    { key: "payment", icon: CreditCard, tone: "neutral" },
    { key: "confirmed", icon: Check, tone: "neutral" },
  ] as const;

  return (
    <motion.div
      className="relative mx-auto w-full max-w-5xl"
      animate={reduceMotion ? undefined : { y: [0, -5, 0] }}
      transition={{ duration: 6, ease: "easeInOut", repeat: Infinity }}
    >
      <div aria-hidden className="absolute -inset-x-2 -bottom-2 top-8 rounded-2xl border border-brand-secondary/35" />
      <div aria-hidden className="absolute -inset-5 -z-10 rounded-[2rem] bg-[radial-gradient(circle_at_35%_20%,hsl(var(--brand)/0.16),transparent_55%),radial-gradient(circle_at_85%_80%,hsl(var(--brand-secondary)/0.13),transparent_48%)] blur-2xl" />
      <div className="group relative overflow-hidden rounded-2xl border border-brand/30 bg-card shadow-soft transition-shadow duration-500 hover:shadow-[0_28px_80px_hsl(var(--brand)/0.14)]">
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 z-20 w-24 bg-gradient-to-r from-transparent via-brand/10 to-transparent blur-xl"
          animate={reduceMotion ? undefined : { x: ["-10rem", "70rem"] }}
          transition={{ duration: 5.5, ease: "easeInOut", repeat: Infinity, repeatDelay: 2 }}
        />
        <div className="flex items-center justify-between border-b border-border px-4 py-3 sm:px-5">
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-md bg-brand-soft text-brand"><MessageCircle className="size-4" /></span>
            <div>
              <p className="text-sm font-semibold">{t("title")}</p>
              <p className="text-xs text-muted-foreground">{t("sample")}</p>
            </div>
          </div>
          <span className="flex items-center gap-1.5 rounded-full border border-brand-secondary/40 bg-card px-2.5 py-1 text-xs font-medium text-brand-secondary">
            <motion.span
              aria-hidden
              className="size-1.5 rounded-full bg-brand-secondary"
              animate={reduceMotion ? undefined : { opacity: [1, 0.35, 1], scale: [1, 0.75, 1] }}
              transition={{ duration: 1.8, repeat: Infinity }}
            />
            {t("connected")}
          </span>
        </div>

        <div className="grid grid-cols-3 border-b border-border bg-surface/70 text-left">
          {[
            ["01", "Chat"],
            ["02", "RMS"],
            ["03", "Booking"],
          ].map(([number, label], index) => (
            <div key={label} className={index === 2 ? "border-l border-brand-secondary/35 px-4 py-3 sm:px-5" : "border-l border-border px-4 py-3 first:border-l-0 sm:px-5"}>
              <span className={index === 2 ? "text-[10px] font-semibold text-brand-secondary" : "text-[10px] font-semibold text-brand"}>{number}</span>
              <p className="mt-0.5 text-xs font-semibold sm:text-sm">{label}</p>
            </div>
          ))}
        </div>

        <div className="grid gap-0 md:grid-cols-[1.05fr_0.95fr]">
          <motion.div
            className="space-y-4 border-b border-border p-4 sm:p-5 md:border-b-0 md:border-r"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, amount: 0.5 }}
            variants={{ visible: { transition: { staggerChildren: 0.16 } } }}
          >
            <motion.div variants={{ hidden: { opacity: 0, x: 18 }, visible: { opacity: 1, x: 0 } }} className="ml-auto max-w-[88%] rounded-xl rounded-br-sm border border-brand-secondary/45 bg-card px-4 py-3 text-sm leading-6">
              {t("customer")}
            </motion.div>
            <motion.div variants={{ hidden: { opacity: 0, x: -18 }, visible: { opacity: 1, x: 0 } }} className="flex items-start gap-2">
              <span className="mt-1 grid size-7 shrink-0 place-items-center rounded-md bg-brand text-brand-foreground"><Bot className="size-3.5" /></span>
              <div className="max-w-[90%] rounded-xl rounded-bl-sm border border-brand/25 bg-brand-soft px-4 py-3 text-sm leading-6">
                {t("assistant")}
              </div>
            </motion.div>
            <motion.div variants={{ hidden: { opacity: 0, y: 8 }, visible: { opacity: 1, y: 0 } }} className="ml-9 flex flex-wrap gap-2 text-xs">
              <span className="rounded-full bg-brand-soft px-2.5 py-1 font-medium text-brand">{t("grounded")}</span>
              <span className="rounded-full border border-brand-secondary/45 bg-card px-2.5 py-1 font-medium text-brand-secondary">{t("actionReady")}</span>
            </motion.div>
          </motion.div>

          <div className="bg-surface p-4 sm:p-5">
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">{t("rmsTitle")}</p>
            <div className="space-y-2">
              {states.map(({ key, icon: Icon, tone }, index) => (
                <motion.div
                  key={key}
                  initial={{ opacity: 0, x: 16 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true, amount: 0.7 }}
                  transition={{ delay: 0.45 + index * 0.12 }}
                  whileHover={{ x: 3 }}
                  className={tone === "pink" ? "flex items-center gap-3 rounded-md border border-brand-secondary/35 bg-card p-3" : "flex items-center gap-3 rounded-md border border-border bg-card p-3"}
                >
                  <span className={tone === "cyan" ? "grid size-8 place-items-center rounded-md bg-brand-soft text-brand" : tone === "pink" ? "grid size-8 place-items-center rounded-md border border-brand-secondary/35 bg-card text-brand-secondary" : "grid size-8 place-items-center rounded-md bg-muted text-muted-foreground"}>
                    <Icon className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{t(`${key}.label`)}</p>
                    <p className="truncate text-xs text-muted-foreground">{t(`${key}.value`)}</p>
                  </div>
                  {index < 2 ? <span className="size-2 rounded-full bg-brand" aria-label={t("verified")} /> : <span className="size-2 rounded-full bg-muted-foreground/30" />}
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-center gap-2 text-xs text-muted-foreground">
        <span className="h-px w-8 bg-brand" />
        <span>{t("flowCaption")}</span>
        <span className="h-px w-8 border-t border-brand-secondary" />
      </div>
    </motion.div>
  );
}
