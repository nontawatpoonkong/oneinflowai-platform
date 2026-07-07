"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Bot, Search, Sparkles, User, type LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

type Phase =
  | { kind: "customer"; key: string }
  | { kind: "status"; key: string; icon: LucideIcon }
  | { kind: "reply"; key: string };

const SEQUENCE: Phase[] = [
  { kind: "customer", key: "customerMessage" },
  { kind: "status", key: "thinking", icon: Sparkles },
  { kind: "status", key: "searching", icon: Search },
  { kind: "status", key: "generating", icon: Bot },
  { kind: "reply", key: "reply" },
];

const DURATIONS = [2200, 1100, 1200, 1200, 3000];

export function ConversationPreview() {
  const t = useTranslations("landing.hero.chat");
  const [step, setStep] = useState(0);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    const timer = setTimeout(
      () => setStep((s) => (s + 1) % SEQUENCE.length),
      DURATIONS[step],
    );
    return () => clearTimeout(timer);
  }, [step]);

  const phase = SEQUENCE[step];

  return (
    <div className="glass-strong w-full max-w-md rounded-3xl p-5 shadow-soft">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="grid size-8 place-items-center rounded-full bg-brand text-brand-foreground">
            <Bot className="size-4" />
          </span>
          <div>
            <p className="text-sm font-semibold leading-none">{t("agentName")}</p>
            <p className="mt-1 text-xs text-muted-foreground">{t("role")}</p>
          </div>
        </div>
        <span className="inline-flex items-center gap-1.5 text-xs text-positive">
          <span className="size-2 animate-pulse-glow rounded-full bg-positive" />
          {t("online")}
        </span>
      </div>

      <div className="flex min-h-52 flex-col justify-end gap-3">
        <div className="flex items-end gap-2">
          <span className="grid size-7 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground">
            <User className="size-3.5" />
          </span>
          <div className="max-w-[80%] rounded-2xl rounded-bl-sm bg-muted px-4 py-2.5 text-sm">
            {t("customerMessage")}
          </div>
        </div>

        <AnimatePresence mode="wait">
          {phase.kind === "status" ? (
            <motion.div
              key={`status-${step}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
              className="ml-9 inline-flex w-fit items-center gap-2 rounded-full bg-brand/10 px-3 py-1.5 text-xs font-medium text-brand"
            >
              <phase.icon className="size-3.5" />
              {t(phase.key)}
              <TypingDots />
            </motion.div>
          ) : phase.kind === "reply" ? (
            <motion.div
              key="reply"
              initial={{ opacity: 0, y: 10, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ type: "spring", stiffness: 200, damping: 18 }}
              className="flex items-end justify-end gap-2"
            >
              <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-brand px-4 py-2.5 text-sm text-brand-foreground shadow-glow">
                {t("reply")}
              </div>
              <span className="grid size-7 shrink-0 place-items-center rounded-full bg-brand text-brand-foreground">
                <Bot className="size-3.5" />
              </span>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>

      <div className="mt-4 flex items-center gap-1.5">
        {SEQUENCE.map((_, i) => (
          <span
            key={i}
            className={cn(
              "h-1 flex-1 rounded-full transition-colors duration-300",
              i <= step ? "bg-brand" : "bg-muted",
            )}
          />
        ))}
      </div>
    </div>
  );
}

function TypingDots() {
  return (
    <span className="flex items-center gap-0.5">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="size-1 rounded-full bg-brand"
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
        />
      ))}
    </span>
  );
}
