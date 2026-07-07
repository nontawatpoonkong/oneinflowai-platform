"use client";

import { motion } from "framer-motion";
import {
  Bot,
  MessageSquare,
  Send,
  Share2,
  Sparkles,
  User,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { Fragment } from "react";

import { VIEWPORT } from "@/lib/animations";

const NODES: { id: string; icon: LucideIcon }[] = [
  { id: "customerIn", icon: User },
  { id: "channel", icon: Share2 },
  { id: "engine", icon: Workflow },
  { id: "knowledge", icon: MessageSquare },
  { id: "openai", icon: Bot },
  { id: "response", icon: Sparkles },
  { id: "customerOut", icon: Send },
];

export function AIPipeline() {
  const t = useTranslations("landing.aiFlow.nodes");

  return (
    <div className="relative">
      <div className="pointer-events-none absolute inset-x-0 top-1/2 hidden h-px -translate-y-1/2 bg-border lg:block">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            aria-hidden
            className="absolute top-1/2 size-2 -translate-y-1/2 rounded-full bg-brand shadow-glow"
            initial={{ left: "0%" }}
            animate={{ left: "100%" }}
            transition={{
              duration: 3.4,
              repeat: Infinity,
              ease: "linear",
              delay: i * 1.1,
            }}
          />
        ))}
      </div>

      <motion.ul
        initial="hidden"
        whileInView="visible"
        viewport={VIEWPORT}
        variants={{ visible: { transition: { staggerChildren: 0.08 } } }}
        className="relative flex flex-col items-stretch gap-3 lg:flex-row lg:items-center lg:justify-between lg:gap-2"
      >
        {NODES.map((node, index) => (
          <Fragment key={node.id}>
            <motion.li
              variants={{
                hidden: { opacity: 0, scale: 0.9 },
                visible: { opacity: 1, scale: 1 },
              }}
              className="glass relative z-10 flex items-center gap-2 rounded-2xl px-4 py-3 shadow-soft lg:flex-col lg:gap-2 lg:px-4 lg:py-4"
            >
              <span className="grid size-9 place-items-center rounded-xl bg-brand/10 text-brand">
                <node.icon className="size-4" />
              </span>
              <span className="text-center text-xs font-medium leading-tight">
                {t(node.id)}
              </span>
            </motion.li>
            {index < NODES.length - 1 ? (
              <span aria-hidden className="mx-auto text-muted-foreground lg:hidden">
                ↓
              </span>
            ) : null}
          </Fragment>
        ))}
      </motion.ul>
    </div>
  );
}
