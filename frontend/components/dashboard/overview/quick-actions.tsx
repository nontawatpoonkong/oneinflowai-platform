"use client";

import { motion } from "framer-motion";
import {
  FileUp,
  MessageCircle,
  UserPlus,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { Card } from "@/components/ui/card";
import { fadeUp, staggerContainer, VIEWPORT } from "@/lib/animations";

interface QuickAction {
  id: string;
  icon: LucideIcon;
  href: string;
}

const ACTIONS: QuickAction[] = [
  { id: "addCustomer", icon: UserPlus, href: "/dashboard/customers" },
  { id: "connectLine", icon: MessageCircle, href: "/dashboard/integrations" },
  { id: "uploadKnowledge", icon: FileUp, href: "/dashboard/knowledge" },
  { id: "inviteTeam", icon: Users, href: "/dashboard/workspace" },
];

export function QuickActions() {
  const t = useTranslations("dashboard.owner.quickActions");

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">{t("title")}</h2>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      <motion.div
        variants={staggerContainer}
        initial="hidden"
        whileInView="visible"
        viewport={VIEWPORT}
        className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        {ACTIONS.map((action) => (
          <motion.div
            key={action.id}
            variants={fadeUp}
            whileHover={{ y: -4 }}
            transition={{ type: "spring", stiffness: 250, damping: 18 }}
          >
            <Link href={action.href}>
              <Card className="group flex items-center gap-4 p-5 transition-colors hover:border-brand/40 hover:shadow-glow">
                <span className="grid size-11 place-items-center rounded-lg bg-brand/10 text-brand transition-transform group-hover:scale-105">
                  <action.icon className="size-5" />
                </span>
                <span className="font-medium">{t(action.id)}</span>
              </Card>
            </Link>
          </motion.div>
        ))}
      </motion.div>
    </section>
  );
}
