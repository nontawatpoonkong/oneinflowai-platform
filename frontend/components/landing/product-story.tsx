"use client";

import {
  ArrowRight,
  BedDouble,
  CheckCircle2,
  ClipboardCheck,
  CreditCard,
  Hotel,
  MessageSquareText,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  UserRound,
  Workflow,
} from "lucide-react";
import { motion } from "framer-motion";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";

type Pillar = { title: string; description: string; points: string[] };
type FlowStep = { title: string; description: string };
type TrustExample = { question: string; tool: string; result: string };
type AutomationFlow = { event: string; action: string };
type PreviewItem = { title: string; description: string; status: string };

const pillarIcons = [MessageSquareText, Hotel, Workflow];
const moduleIcons = [ClipboardCheck, UserRound, CreditCard, BedDouble, Hotel, Sparkles, RefreshCw];

function SectionIntro({ eyebrow, title, description, pink = false }: { eyebrow: string; title: string; description: string; pink?: boolean }) {
  return (
    <motion.div
      className="max-w-3xl"
      initial={{ opacity: 0, y: 22 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.35 }}
    >
      <Badge variant={pink ? "outline" : "default"} className={pink ? "border-brand-secondary/50 bg-card text-brand-secondary" : undefined}>{eyebrow}</Badge>
      <h2 className="mt-4 text-balance text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h2>
      <p className="mt-4 max-w-2xl text-pretty text-base leading-7 text-muted-foreground sm:text-lg">{description}</p>
    </motion.div>
  );
}

export function ProductStory() {
  const t = useTranslations("landing.story");
  const painPoints = t.raw("problem.points") as string[];
  const pillars = t.raw("pillars.items") as Pillar[];
  const workflow = t.raw("workflow.steps") as FlowStep[];
  const trustExamples = t.raw("trustedAi.examples") as TrustExample[];
  const modules = t.raw("operations.modules") as string[];
  const lifecycle = t.raw("operations.lifecycle") as string[];
  const customer360 = t.raw("customerAutomation.customer360.points") as string[];
  const automationFlows = t.raw("customerAutomation.automation.flows") as AutomationFlow[];
  const disconnected = t.raw("comparison.disconnected") as string[];
  const connected = t.raw("comparison.connected") as string[];
  const previewItems = t.raw("preview.items") as PreviewItem[];
  const audiences = t.raw("audienceControl.audiences") as string[];
  const controls = t.raw("audienceControl.controls") as string[];

  return (
    <>
      <section className="border-b border-border bg-surface py-16 sm:py-20">
        <div className="container-wide grid gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:items-start">
          <SectionIntro eyebrow={t("problem.eyebrow")} title={t("problem.title")} description={t("problem.description")} pink />
          <div className="grid gap-3 sm:grid-cols-2">
            {painPoints.map((point, index) => (
              <motion.div
                key={point}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.45 }}
                transition={{ delay: index * 0.06 }}
                whileHover={{ y: -3 }}
                className={index % 3 === 0 ? "flex gap-3 rounded-lg border border-brand-secondary/35 bg-card p-4 shadow-sm transition-shadow hover:shadow-md" : "flex gap-3 rounded-lg border border-brand/20 bg-card p-4 shadow-sm transition-shadow hover:shadow-md"}
              >
                <span className={index % 3 === 0 ? "mt-0.5 grid size-7 shrink-0 place-items-center rounded-md border border-brand-secondary/40 bg-card text-xs font-semibold text-brand-secondary" : "mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-brand-soft text-xs font-semibold text-brand"}>{index + 1}</span>
                <p className="text-sm leading-6">{point}</p>
              </motion.div>
            ))}
            <motion.div
              initial={{ opacity: 0, scale: 0.98 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true, amount: 0.6 }}
              className="sm:col-span-2 flex items-center gap-3 rounded-lg border border-brand/30 bg-brand-soft p-4 font-medium"
            >
              <ArrowRight className="size-5 shrink-0 text-brand" />
              {t("problem.transition")}
            </motion.div>
          </div>
        </div>
      </section>

      <section id="product" className="container-wide scroll-mt-20 py-16 sm:py-24">
        <SectionIntro eyebrow={t("pillars.eyebrow")} title={t("pillars.title")} description={t("pillars.description")} />
        <div className="mt-10 grid gap-4 lg:grid-cols-3">
          {pillars.map((pillar, index) => {
            const Icon = pillarIcons[index] ?? Workflow;
            const pink = index === 1;
            return (
              <motion.article
                key={pillar.title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.35 }}
                transition={{ delay: index * 0.1 }}
                whileHover={{ y: -6, scale: 1.01 }}
                className={pink ? "rounded-xl border border-brand-secondary/40 bg-card p-6 shadow-sm transition-shadow hover:shadow-[0_18px_50px_hsl(var(--brand-secondary)/0.12)]" : "rounded-xl border border-brand/20 bg-card p-6 shadow-sm transition-shadow hover:shadow-[0_18px_50px_hsl(var(--brand)/0.12)]"}
              >
                <span className={pink ? "grid size-10 place-items-center rounded-md border border-brand-secondary/40 bg-card text-brand-secondary" : "grid size-10 place-items-center rounded-md bg-brand-soft text-brand"}><Icon className="size-5" /></span>
                <h3 className="mt-5 text-xl font-semibold">{pillar.title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{pillar.description}</p>
                <ul className="mt-5 space-y-2">
                  {pillar.points.map((point) => <li key={point} className="flex gap-2 text-sm"><CheckCircle2 className={pink ? "mt-0.5 size-4 shrink-0 text-brand-secondary" : "mt-0.5 size-4 shrink-0 text-brand"} /><span>{point}</span></li>)}
                </ul>
              </motion.article>
            );
          })}
        </div>
      </section>

      <section id="workflow" className="relative scroll-mt-20 overflow-hidden border-y border-border bg-foreground py-16 text-background sm:py-24">
        <motion.div
          aria-hidden
          className="absolute -right-20 top-0 size-72 rounded-full bg-brand/10 blur-3xl"
          animate={{ x: [0, -35, 0], y: [0, 20, 0] }}
          transition={{ duration: 12, ease: "easeInOut", repeat: Infinity }}
        />
        <div className="container-wide relative">
          <div className="max-w-3xl">
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">{t("workflow.eyebrow")}</span>
            <h2 className="mt-4 text-balance text-3xl font-semibold sm:text-4xl">{t("workflow.title")}</h2>
            <p className="mt-4 text-base leading-7 text-background/65 sm:text-lg">{t("workflow.description")}</p>
          </div>
          <ol className="mt-10 grid gap-px overflow-hidden rounded-xl border border-background/15 bg-background/15 sm:grid-cols-2 lg:grid-cols-4">
            {workflow.map((step, index) => (
              <motion.li
                key={step.title}
                initial={{ opacity: 0, y: 18 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.4 }}
                transition={{ delay: index * 0.07 }}
                whileHover={{ backgroundColor: "hsl(var(--background) / 0.06)" }}
                className="relative bg-foreground p-5"
              >
                <span className={index % 3 === 1 ? "text-sm font-semibold text-brand-secondary" : "text-sm font-semibold text-brand"}>{String(index + 1).padStart(2, "0")}</span>
                <h3 className="mt-4 font-semibold">{step.title}</h3>
                <p className="mt-2 text-sm leading-6 text-background/60">{step.description}</p>
              </motion.li>
            ))}
          </ol>
        </div>
      </section>

      <section className="container-wide py-16 sm:py-24">
        <div className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:items-center">
          <SectionIntro eyebrow={t("trustedAi.eyebrow")} title={t("trustedAi.title")} description={t("trustedAi.description")} pink />
          <motion.div
            initial={{ opacity: 0, x: 28 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6"
          >
            <div className="grid grid-cols-1 items-center gap-2 text-center text-xs sm:grid-cols-[1fr_auto_1fr_auto_1fr] sm:text-sm">
              <div className="rounded-md border border-brand-secondary/40 bg-card px-3 py-3 font-medium text-brand-secondary">{t("trustedAi.pipeline.understand")}</div>
              <ArrowRight className="mx-auto hidden size-4 text-muted-foreground sm:block" />
              <div className="rounded-md bg-brand-soft px-3 py-3 font-medium text-brand">{t("trustedAi.pipeline.tool")}</div>
              <ArrowRight className="mx-auto hidden size-4 text-muted-foreground sm:block" />
              <div className="rounded-md bg-muted px-3 py-3 font-medium">{t("trustedAi.pipeline.result")}</div>
            </div>
            <div className="mt-5 divide-y divide-border">
              {trustExamples.map((example) => (
                <div key={example.question} className="grid gap-2 py-3 text-sm sm:grid-cols-[1fr_auto_1fr_auto_1fr] sm:items-center">
                  <span>{example.question}</span><ArrowRight className="hidden size-3.5 text-muted-foreground sm:block" /><span className="font-medium text-brand">{example.tool}</span><ArrowRight className="hidden size-3.5 text-muted-foreground sm:block" /><span className="text-muted-foreground">{example.result}</span>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </section>

      <section id="hotel" className="scroll-mt-20 border-y border-border bg-surface py-16 sm:py-24">
        <div className="container-wide">
          <SectionIntro eyebrow={t("operations.eyebrow")} title={t("operations.title")} description={t("operations.description")} />
          <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-7">
            {modules.map((module, index) => {
              const Icon = moduleIcons[index] ?? Hotel;
              return <motion.div key={module} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.5 }} transition={{ delay: index * 0.06 }} whileHover={{ y: -4 }} className="flex items-center gap-3 rounded-lg border border-border bg-card p-4 shadow-sm lg:flex-col lg:items-start"><Icon className={index === 2 || index === 4 ? "size-5 text-brand-secondary" : "size-5 text-brand"} /><span className="text-sm font-semibold">{module}</span></motion.div>;
            })}
          </div>
          <div className="mt-8 flex flex-wrap items-center gap-2">
            {lifecycle.map((state, index) => <div key={state} className="flex items-center gap-2"><span className={index === lifecycle.length - 2 ? "rounded-full border border-brand-secondary/45 bg-card px-3 py-1.5 text-xs font-medium text-brand-secondary" : "rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium"}>{state}</span>{index < lifecycle.length - 1 ? <ArrowRight className="size-3.5 text-muted-foreground" /> : null}</div>)}
          </div>
        </div>
      </section>

      <section className="container-wide py-16 sm:py-24">
        <div className="grid gap-5 lg:grid-cols-2">
          <motion.article initial={{ opacity: 0, x: -24 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true, amount: 0.3 }} whileHover={{ y: -4 }} className="rounded-xl border border-border bg-card p-6 shadow-sm transition-shadow hover:shadow-lg">
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-secondary">{t("customerAutomation.customer360.eyebrow")}</span>
            <h2 className="mt-3 text-2xl font-semibold">{t("customerAutomation.customer360.title")}</h2>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">{t("customerAutomation.customer360.description")}</p>
            <div className="mt-5 flex flex-wrap gap-2">{customer360.map((point) => <span key={point} className="rounded-full border border-brand-secondary/40 bg-card px-3 py-1.5 text-xs font-medium text-brand-secondary">{point}</span>)}</div>
          </motion.article>
          <motion.article initial={{ opacity: 0, x: 24 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true, amount: 0.3 }} whileHover={{ y: -4 }} className="rounded-xl border border-border bg-card p-6 shadow-sm transition-shadow hover:shadow-lg">
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">{t("customerAutomation.automation.eyebrow")}</span>
            <h2 className="mt-3 text-2xl font-semibold">{t("customerAutomation.automation.title")}</h2>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">{t("customerAutomation.automation.description")}</p>
            <div className="mt-5 space-y-2">{automationFlows.map((flow) => <div key={flow.event} className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 rounded-md bg-surface p-3 text-sm"><span className="font-medium">{flow.event}</span><ArrowRight className="size-3.5 text-brand" /><span className="text-muted-foreground">{flow.action}</span></div>)}</div>
          </motion.article>
        </div>
      </section>

      <section className="border-y border-border bg-brand-soft/70 py-16 sm:py-24">
        <div className="container-wide">
          <SectionIntro eyebrow={t("comparison.eyebrow")} title={t("comparison.title")} description={t("comparison.description")} pink />
          <motion.div initial={{ opacity: 0, y: 22 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.3 }} className="mt-10 grid overflow-hidden rounded-xl border border-brand-secondary/40 bg-card shadow-sm lg:grid-cols-2">
            <div className="border-b border-border p-6 lg:border-b-0 lg:border-r"><h3 className="font-semibold text-muted-foreground">{t("comparison.disconnectedTitle")}</h3><ul className="mt-4 space-y-3">{disconnected.map((item) => <li key={item} className="flex gap-2 text-sm text-muted-foreground"><span className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground/50" />{item}</li>)}</ul></div>
            <div className="p-6"><h3 className="font-semibold text-brand-secondary">OneInFlowAI</h3><ul className="mt-4 space-y-3">{connected.map((item) => <li key={item} className="flex gap-2 text-sm"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand" />{item}</li>)}</ul><p className="mt-5 border-l-2 border-brand-secondary pl-4 font-semibold">{t("comparison.punchline")}</p></div>
          </motion.div>
        </div>
      </section>

      <section id="features" className="container-wide scroll-mt-20 py-16 sm:py-24">
        <SectionIntro eyebrow={t("preview.eyebrow")} title={t("preview.title")} description={t("preview.description")} />
        <div className="mt-10 overflow-hidden rounded-xl border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border px-5 py-3"><span className="text-sm font-semibold">OneInFlowAI</span><span className="rounded-full bg-brand-soft px-2.5 py-1 text-xs font-medium text-brand">{t("preview.workspace")}</span></div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3">
            {previewItems.map((item, index) => <motion.div key={item.title} initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.5 }} transition={{ delay: index * 0.06 }} whileHover={{ backgroundColor: "hsl(var(--brand) / 0.045)" }} className="border-b border-border p-5 sm:border-r lg:[&:nth-child(3n)]:border-r-0"><div className="flex items-start justify-between gap-3"><h3 className="font-semibold">{item.title}</h3><span className={index % 3 === 1 ? "rounded-full border border-brand-secondary/40 bg-card px-2 py-1 text-[11px] font-medium text-brand-secondary" : "rounded-full bg-brand-soft px-2 py-1 text-[11px] font-medium text-brand"}>{item.status}</span></div><p className="mt-2 text-sm leading-6 text-muted-foreground">{item.description}</p></motion.div>)}
          </div>
        </div>
      </section>

      <section className="border-y border-border bg-surface py-16 sm:py-24">
        <div className="container-wide grid gap-10 lg:grid-cols-2">
          <div><SectionIntro eyebrow={t("audienceControl.audienceEyebrow")} title={t("audienceControl.audienceTitle")} description={t("audienceControl.audienceDescription")} /><div className="mt-6 flex flex-wrap gap-2">{audiences.map((audience) => <span key={audience} className="rounded-full border border-border bg-card px-3 py-2 text-sm font-medium">{audience}</span>)}</div></div>
          <motion.div initial={{ opacity: 0, x: 24 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true, amount: 0.3 }} className="rounded-xl border border-border bg-card p-6 shadow-sm"><span className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-secondary">{t("audienceControl.controlEyebrow")}</span><h2 className="mt-3 text-2xl font-semibold">{t("audienceControl.controlTitle")}</h2><p className="mt-3 text-sm leading-6 text-muted-foreground">{t("audienceControl.controlDescription")}</p><ul className="mt-5 space-y-3">{controls.map((control) => <li key={control} className="flex gap-2 text-sm"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-brand-secondary" />{control}</li>)}</ul></motion.div>
        </div>
      </section>
    </>
  );
}
