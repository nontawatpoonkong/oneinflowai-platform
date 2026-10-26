"use client";

import { AlertTriangle, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { PlatformMarketingConsole } from "@/components/platform/platform-marketing";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  usePlatformMutation,
  usePlatformOverview,
  usePlatformPage,
  usePlatformSnapshot,
} from "@/hooks/api/use-platform";
import type { PlatformRecord } from "@/types/platform";

const listConfig = {
  users: { title: "Users", description: "Safe account, billing, Workspace, usage and audit context.", path: "/platform/users" },
  workspaces: { title: "Workspaces", description: "Cross-tenant lifecycle and operational context without guest PII.", path: "/platform/workspaces" },
  subscriptions: { title: "Subscriptions", description: "Manual Pilot activation under the existing billing state machine.", path: "/platform/subscriptions" },
  audit: { title: "Global audit", description: "Immutable events across Workspaces and platform operations.", path: "/platform/audit/events" },
} as const;

type ListSection = keyof typeof listConfig;

function State({ error = false }: { error?: boolean }) {
  const Icon = error ? AlertTriangle : Loader2;
  return <div className="grid min-h-56 place-items-center rounded-lg border border-dashed"><Icon className={error ? "size-7 text-destructive" : "size-7 animate-spin text-cyan-500"} /><span className="sr-only">{error ? "Unable to load" : "Loading"}</span></div>;
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Status({ value }: { value: unknown }) {
  return <Badge variant="outline">{renderValue(value)}</Badge>;
}

function requestReason(impact: string): string | null {
  if (!window.confirm(`${impact}\n\nThis operation is audited. Continue?`)) return null;
  const reason = window.prompt("Required reason (minimum 3 characters):")?.trim();
  return reason && reason.length >= 3 ? reason : null;
}

function RowActions({ section, item }: { section: ListSection; item: PlatformRecord }) {
  const mutation = usePlatformMutation();
  const id = String(item.id ?? "");
  const status = String(item.status ?? "");
  if (!id || section === "audit") return null;
  let action: { label: string; path: string; impact: string } | null = null;
  if (section === "users") {
    action = status === "ACTIVE"
      ? { label: "Suspend", path: `/platform/users/${id}/suspend`, impact: "The user will be signed out on their next authenticated request." }
      : { label: "Reactivate", path: `/platform/users/${id}/reactivate`, impact: "The user will regain account access." };
  }
  if (section === "workspaces") {
    action = status === "ACTIVE"
      ? { label: "Suspend", path: `/platform/workspaces/${id}/suspend`, impact: "Members, public AI ingress, and new automation claims will be blocked." }
      : { label: "Reactivate", path: `/platform/workspaces/${id}/reactivate`, impact: "Workspace operations will resume." };
  }
  if (section === "subscriptions" && status === "PENDING_ACTIVATION") {
    action = { label: "Activate Pilot", path: `/platform/subscriptions/${id}/activate`, impact: "The subscription period will start now. This does not record SaaS payment revenue." };
  }
  if (!action) return null;
  return <Button size="sm" variant="outline" disabled={mutation.isPending} onClick={() => { const reason = requestReason(action!.impact); if (reason) mutation.mutate({ path: action!.path, reason }); }}>{action.label}</Button>;
}

export function PlatformListView({ section }: { section: ListSection }) {
  const [page, setPage] = useState(1);
  const config = listConfig[section];
  const query = usePlatformPage(config.path, page);
  if (query.isLoading) return <State />;
  if (query.isError || !query.data) return <State error />;
  const visibleKeys = Array.from(new Set(query.data.items.flatMap((item) => Object.keys(item)))).filter((key) => !["safe_metadata"].includes(key)).slice(0, 9);
  return <section className="space-y-5"><header><h1 className="text-2xl font-semibold">{config.title}</h1><p className="mt-1 text-sm text-muted-foreground">{config.description}</p></header><div className="overflow-x-auto rounded-lg border bg-card"><table className="w-full min-w-[850px] text-left text-sm"><thead className="border-b bg-muted/40"><tr>{visibleKeys.map((key) => <th key={key} className="px-3 py-2 font-medium">{key.replaceAll("_", " ")}</th>)}<th className="px-3 py-2"><span className="sr-only">Actions</span></th></tr></thead><tbody>{query.data.items.map((item, index) => <tr key={String(item.id ?? index)} className="border-b last:border-b-0 hover:bg-muted/20">{visibleKeys.map((key) => <td key={key} className="max-w-64 truncate px-3 py-2">{key === "status" || key === "result" ? <Status value={item[key]} /> : renderValue(item[key])}</td>)}<td className="px-3 py-2 text-right"><RowActions section={section} item={item} /></td></tr>)}</tbody></table>{query.data.items.length === 0 ? <p className="p-10 text-center text-sm text-muted-foreground">No records match this view.</p> : null}</div><div className="flex items-center justify-between text-sm text-muted-foreground"><span>{query.data.total} records · page {query.data.page} of {Math.max(query.data.total_pages, 1)}</span><div className="flex gap-2"><Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft /> Previous</Button><Button size="sm" variant="outline" disabled={page >= query.data.total_pages} onClick={() => setPage((value) => value + 1)}>Next <ChevronRight /></Button></div></div></section>;
}

export function PlatformOverviewView() {
  const query = usePlatformOverview();
  if (query.isLoading) return <State />;
  if (query.isError || !query.data) return <State error />;
  return <section className="space-y-7"><header><p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-600">Control center</p><h1 className="mt-1 text-2xl font-semibold">Platform overview</h1><p className="mt-1 text-sm text-muted-foreground">Immediate operations first; every value comes from authoritative persisted data.</p></header><div><h2 className="mb-3 text-sm font-semibold uppercase tracking-wide">Needs attention</h2><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{Object.entries(query.data.needs_attention).map(([key, value]) => <Link key={key} href={query.data.links[key.replace("pending_subscription_activations", "pending_subscriptions")] ?? "/platform/operations"} className="rounded-lg border border-pink-500/30 bg-card p-4 transition hover:border-pink-500"><p className="text-2xl font-semibold">{value}</p><p className="mt-1 text-xs text-muted-foreground">{key.replaceAll("_", " ")}</p></Link>)}</div></div><div><h2 className="mb-3 text-sm font-semibold uppercase tracking-wide">SaaS and network metrics</h2><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{Object.entries(query.data.metrics).map(([key, value]) => <article key={key} className="rounded-lg border border-cyan-500/20 bg-card p-4"><p className="break-words text-xl font-semibold">{renderValue(value)}</p><p className="mt-1 text-xs text-muted-foreground">{key.replaceAll("_", " ")}</p></article>)}</div></div></section>;
}

const snapshots = {
  analytics: ["Analytics", "SaaS funnel, UTC active-user windows, product usage and hotel network value kept separate from SaaS revenue.", "/platform/analytics"],
  operations: ["Operations", "AI, automation workers, PMS and channel health without credentials or hidden reasoning.", "/platform/operations"],
  system: ["System", "Read-only platform health. Deployment secrets and configuration remain outside the product UI.", "/platform/system/health"],
} as const;

export function PlatformSnapshotView({ section }: { section: keyof typeof snapshots }) {
  const [title, description, path] = snapshots[section];
  const query = usePlatformSnapshot(path);
  if (query.isLoading) return <State />;
  if (query.isError || !query.data) return <State error />;
  return <section className="space-y-5"><header><h1 className="text-2xl font-semibold">{title}</h1><p className="mt-1 text-sm text-muted-foreground">{description}</p></header><div className="grid gap-4 xl:grid-cols-2">{Object.entries(query.data).map(([key, value]) => <article key={key} className="overflow-hidden rounded-lg border bg-card"><h2 className="border-b bg-muted/30 px-4 py-3 text-sm font-semibold">{key.replaceAll("_", " ")}</h2><pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words p-4 text-xs leading-5">{JSON.stringify(value, null, 2)}</pre></article>)}</div></section>;
}

function ReadOnlyTable({ title, path }: { title: string; path: string }) {
  const query = usePlatformPage(path, 1);
  if (query.isLoading) return <State />;
  if (query.isError || !query.data) return <State error />;
  const keys = Array.from(
    new Set(query.data.items.flatMap((item) => Object.keys(item))),
  ).slice(0, 8);
  return <div className="overflow-x-auto rounded-lg border bg-card"><h2 className="border-b px-4 py-3 font-semibold">{title}</h2><table className="w-full min-w-[760px] text-left text-sm"><thead className="border-b bg-muted/40"><tr>{keys.map((key) => <th key={key} className="p-3">{key.replaceAll("_", " ")}</th>)}</tr></thead><tbody>{query.data.items.map((item, index) => <tr key={String(item.id ?? index)} className="border-b last:border-0">{keys.map((key) => <td key={key} className="max-w-64 truncate p-3">{renderValue(item[key])}</td>)}</tr>)}</tbody></table>{query.data.items.length === 0 ? <p className="p-8 text-center text-sm text-muted-foreground">No records.</p> : null}</div>;
}

export function PlatformMarketingView() {
  return <div className="space-y-7"><PlatformMarketingConsole /><ReadOnlyTable title="Attribution by Workspace, source and currency" path="/platform/marketing/attribution" /></div>;
}

export function PlatformSubscriptionsView() {
  return <div className="space-y-7"><PlatformListView section="subscriptions" /><section className="space-y-3"><header><h2 className="text-lg font-semibold">Plan catalog</h2><p className="text-sm text-muted-foreground">Read-only because the current catalog is code-seeded. Mutation is deferred to avoid a second pricing authority.</p></header><ReadOnlyTable title="Plans and entitlements" path="/platform/plans" /></section></div>;
}
