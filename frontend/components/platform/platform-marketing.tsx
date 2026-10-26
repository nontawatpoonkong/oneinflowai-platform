"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ChevronLeft, ChevronRight, Loader2, Plus, ShieldAlert, X } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/services/api/errors";
import { platformMarketingService as service } from "@/services/platform/marketing.service";
import type { CampaignAnalytics, CampaignDetail, CampaignStatus, CatalogTarget, CatalogTargetKind, CodeListItem, CodeStatus, PlatformPage } from "@/types/platform";

type Tab = "campaigns" | "codes" | "analytics";
const CAMPAIGN_STATUSES: CampaignStatus[] = ["DRAFT", "ACTIVE", "PAUSED", "EXPIRED", "ARCHIVED"];
const CODE_STATUSES: CodeStatus[] = ["ACTIVE", "DISABLED", "EXHAUSTED", "EXPIRED", "ARCHIVED"];
const SOURCES = ["DIRECT", "WEBCHAT", "LINE", "FACEBOOK", "INSTAGRAM", "PARTNER", "MANUAL", "OTHER"];
const selectClass = "h-10 rounded-md border border-input bg-background px-3 text-sm";
const errorText = (error: unknown) => (error instanceof ApiError ? `${error.message} (${error.code})` : "Request failed");
const when = (value: string | null | undefined) => (value ? new Date(value).toLocaleString() : "—");
const isoOrNull = (value: string) => (value ? new Date(value).toISOString() : null);

export function PlatformMarketingConsole() {
  const [tab, setTab] = useState<Tab>("campaigns");
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <section className="space-y-5">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-600">Campaign governance</p>
        <h1 className="mt-1 text-2xl font-semibold">Marketing</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">Every campaign is owned and funded by one Workspace. Platform operators can author drafts and reduce discount exposure; only the owning Workspace can activate, resume, or re-enable a discount.</p>
      </header>
      <nav aria-label="Marketing sections" className="flex gap-1 rounded-lg border bg-card p-1">
        {(["campaigns", "codes", "analytics"] as Tab[]).map((item) => (
          <button key={item} type="button" aria-pressed={tab === item} onClick={() => setTab(item)} className={`rounded-md px-4 py-2 text-sm font-medium capitalize ${tab === item ? "bg-cyan-500 text-slate-950" : "text-muted-foreground hover:bg-muted"}`}>{item}</button>
        ))}
      </nav>
      {tab === "campaigns" ? <CampaignList onOpen={setSelected} /> : tab === "codes" ? <CodeList /> : <Analytics />}
      {selected ? <CampaignDrawer id={selected} onClose={() => setSelected(null)} /> : null}
    </section>
  );
}

function State({ error, retry }: { error?: unknown; retry?: () => void }) {
  if (error) {
    const denied = error instanceof ApiError && error.status === 403;
    return <div className="grid min-h-40 place-items-center rounded-lg border border-dashed p-6 text-center" role="alert"><div><AlertTriangle className="mx-auto size-6 text-destructive" /><p className="mt-2 text-sm">{denied ? "Platform administrator authority is required." : errorText(error)}</p>{retry && !denied ? <Button className="mt-3" size="sm" variant="outline" onClick={retry}>Retry</Button> : null}</div></div>;
  }
  return <div className="grid min-h-40 place-items-center rounded-lg border border-dashed" role="status"><Loader2 className="size-6 animate-spin text-cyan-500" /><span className="sr-only">Loading</span></div>;
}

function Pager({ page, data, onPage }: { page: number; data: PlatformPage<unknown>; onPage: (value: number) => void }) {
  return <div className="flex items-center justify-between text-sm text-muted-foreground"><span>{data.total} records · page {data.page} of {Math.max(data.total_pages, 1)}</span><div className="flex gap-2"><Button size="sm" variant="outline" disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft /> Previous</Button><Button size="sm" variant="outline" disabled={page >= data.total_pages} onClick={() => onPage(page + 1)}>Next <ChevronRight /></Button></div></div>;
}

function useInvalidate() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ["platform-marketing"] });
}

/** Reason + explicit confirmation for every audited platform mutation. */
function ReasonDialog({ title, impact, busy, error, onSubmit, onCancel }: { title: string; impact: string; busy: boolean; error: unknown; onSubmit: (reason: string) => void; onCancel: () => void }) {
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const valid = reason.trim().length >= 3 && confirmed;
  return (
    <div className="space-y-3 rounded-lg border border-pink-500/40 bg-pink-500/5 p-4 text-sm" role="dialog" aria-label={title}>
      <h3 className="font-semibold">{title}</h3>
      <p className="text-muted-foreground">{impact}</p>
      <div className="space-y-1.5"><Label htmlFor="platform-reason">Reason (audited)</Label><Input id="platform-reason" maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} /></div>
      <label className="flex items-center gap-2"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />I confirm this operation</label>
      {error ? <p className="text-destructive" role="alert">{errorText(error)}</p> : null}
      <div className="flex gap-2"><Button size="sm" disabled={!valid || busy} onClick={() => onSubmit(reason.trim())}>{busy ? <Loader2 className="size-4 animate-spin" /> : null}Confirm</Button><Button size="sm" variant="ghost" disabled={busy} onClick={onCancel}>Cancel</Button></div>
    </div>
  );
}

function CampaignList({ onOpen }: { onOpen: (id: string) => void }) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [origin, setOrigin] = useState("");
  const [creating, setCreating] = useState(false);
  const term = search.trim().length >= 2 ? search.trim() : undefined;
  const query = useQuery({ queryKey: ["platform-marketing", "campaigns", page, term, status, origin], queryFn: () => service.campaigns({ page, page_size: 25, search: term, status, origin }) });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5"><Label htmlFor="campaign-search">Search</Label><Input id="campaign-search" className="w-64" placeholder="Campaign or Workspace" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></div>
        <div className="space-y-1.5"><Label htmlFor="campaign-status">Status</Label><select id="campaign-status" className={selectClass} value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">All</option>{CAMPAIGN_STATUSES.map((item) => <option key={item}>{item}</option>)}</select></div>
        <div className="space-y-1.5"><Label htmlFor="campaign-origin">Authored by</Label><select id="campaign-origin" className={selectClass} value={origin} onChange={(event) => { setOrigin(event.target.value); setPage(1); }}><option value="">All</option><option value="WORKSPACE">Workspace</option><option value="PLATFORM">Platform</option></select></div>
        <Button className="ml-auto" onClick={() => setCreating(true)}><Plus className="size-4" />New draft campaign</Button>
      </div>
      {creating ? <CreateCampaign onClose={() => setCreating(false)} onCreated={(id) => { setCreating(false); onOpen(id); }} /> : null}
      {query.isLoading ? <State /> : query.isError || !query.data ? <State error={query.error} retry={() => query.refetch()} /> : (
        <>
          <div className="overflow-x-auto rounded-lg border bg-card">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="border-b bg-muted/40"><tr><th className="p-3">Campaign</th><th className="p-3">Workspace</th><th className="p-3">Status</th><th className="p-3">Window</th><th className="p-3">Codes</th><th className="p-3">Confirmed</th><th className="p-3">Reserved now</th></tr></thead>
              <tbody>{query.data.items.map((item) => (
                <tr key={item.id} className="cursor-pointer border-b last:border-0 hover:bg-muted/30" onClick={() => onOpen(item.id)}>
                  <td className="p-3"><button type="button" className="text-left font-medium underline-offset-2 hover:underline" onClick={() => onOpen(item.id)}>{item.name}</button>{item.origin === "PLATFORM" ? <Badge variant="outline" className="ml-2 border-pink-500/40 text-pink-600">Platform-authored</Badge> : null}</td>
                  <td className="p-3">{item.workspace}</td>
                  <td className="p-3"><Badge variant="outline">{item.status}</Badge></td>
                  <td className="p-3 text-xs">{when(item.valid_from)} → {when(item.valid_until)}</td>
                  <td className="p-3">{item.codes}</td><td className="p-3">{item.confirmed_uses}</td><td className="p-3">{item.active_reservations}</td>
                </tr>
              ))}</tbody>
            </table>
            {query.data.items.length === 0 ? <p className="p-10 text-center text-sm text-muted-foreground">No campaigns match this view.</p> : null}
          </div>
          <Pager page={page} data={query.data} onPage={setPage} />
        </>
      )}
    </div>
  );
}

function CreateCampaign({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const invalidate = useInvalidate();
  const [workspaceSearch, setWorkspaceSearch] = useState("");
  const [workspace, setWorkspace] = useState<{ id: string; name: string } | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [validFrom, setValidFrom] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const term = workspaceSearch.trim();
  const workspaces = useQuery({ queryKey: ["platform-marketing", "workspaces", term], queryFn: () => service.workspaces(term), enabled: term.length >= 2 && !workspace });
  const create = useMutation({
    mutationFn: () => service.createCampaign({ workspace_id: workspace!.id, name: name.trim(), description: description.trim() || null, valid_from: isoOrNull(validFrom), valid_until: isoOrNull(validUntil), reason: reason.trim(), confirmed }),
    onSuccess: (detail) => { invalidate(); onCreated(detail.campaign.id); },
  });
  const windowError = validFrom && validUntil && validUntil <= validFrom ? "End must be after start." : null;
  const valid = workspace && name.trim() && reason.trim().length >= 3 && confirmed && !windowError;
  const submit = (event: FormEvent) => { event.preventDefault(); if (valid) create.mutate(); };
  return (
    <form onSubmit={submit} className="space-y-4 rounded-lg border border-cyan-500/40 bg-card p-4">
      <div className="flex items-center justify-between"><h2 className="font-semibold">New platform-authored draft</h2><Button type="button" size="icon" variant="ghost" aria-label="Close" onClick={onClose}><X /></Button></div>
      <p className="flex gap-2 rounded-md bg-muted/50 p-3 text-xs text-muted-foreground"><ShieldAlert className="size-4 shrink-0 text-pink-500" />The campaign is created as DRAFT inside the selected Workspace. Its discount would reduce that Workspace&apos;s revenue, so it stays inactive until the Workspace activates it.</p>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-1.5"><Label htmlFor="ws-search">Owning Workspace</Label>{workspace ? <div className="flex h-10 items-center justify-between rounded-md border px-3 text-sm"><span>{workspace.name}</span><Button type="button" size="sm" variant="ghost" onClick={() => setWorkspace(null)}>Change</Button></div> : <><Input id="ws-search" placeholder="Search active Workspaces" value={workspaceSearch} onChange={(event) => setWorkspaceSearch(event.target.value)} />{workspaces.isError ? <p className="text-xs text-destructive">{errorText(workspaces.error)}</p> : null}{workspaces.data ? <ul className="max-h-40 divide-y overflow-auto rounded-md border">{workspaces.data.items.length === 0 ? <li className="p-2 text-sm text-muted-foreground">No active Workspaces match.</li> : workspaces.data.items.map((item) => <li key={String(item.id)}><button type="button" className="w-full p-2 text-left text-sm hover:bg-muted" onClick={() => setWorkspace({ id: String(item.id), name: String(item.name) })}>{String(item.name)}</button></li>)}</ul> : null}</>}</div>
        <div className="space-y-1.5"><Label htmlFor="new-name">Name</Label><Input id="new-name" maxLength={255} value={name} onChange={(event) => setName(event.target.value)} /></div>
        <div className="space-y-1.5 md:col-span-2"><Label htmlFor="new-desc">Description</Label><Input id="new-desc" maxLength={2000} value={description} onChange={(event) => setDescription(event.target.value)} /></div>
        <div className="space-y-1.5"><Label htmlFor="new-from">Valid from (local time)</Label><Input id="new-from" type="datetime-local" value={validFrom} onChange={(event) => setValidFrom(event.target.value)} /></div>
        <div className="space-y-1.5"><Label htmlFor="new-until">Valid until (local time)</Label><Input id="new-until" type="datetime-local" value={validUntil} onChange={(event) => setValidUntil(event.target.value)} />{windowError ? <p className="text-xs text-destructive">{windowError}</p> : null}</div>
        <div className="space-y-1.5 md:col-span-2"><Label htmlFor="new-reason">Reason (audited)</Label><Input id="new-reason" maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} /></div>
      </div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />I confirm this draft is requested by or agreed with the Workspace</label>
      {create.isError ? <p className="text-sm text-destructive" role="alert">{errorText(create.error)}</p> : null}
      <Button type="submit" disabled={!valid || create.isPending}>{create.isPending ? <Loader2 className="size-4 animate-spin" /> : null}Create draft</Button>
    </form>
  );
}

function CampaignDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const invalidate = useInvalidate();
  const query = useQuery({ queryKey: ["platform-marketing", "campaign", id], queryFn: () => service.campaign(id) });
  const [action, setAction] = useState<"pause" | "expire" | "archive" | null>(null);
  const transition = useMutation({ mutationFn: ({ verb, reason }: { verb: "pause" | "expire" | "archive"; reason: string }) => service.transitionCampaign(id, verb, reason), onSuccess: () => { setAction(null); invalidate(); } });
  const impacts = { pause: "New validations and Holds stop immediately. Existing Holds and redemptions are unchanged.", expire: "Permanently ends the campaign window. It can then only be archived.", archive: "Terminal. Historical redemptions and Booking price snapshots are preserved." };
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40" role="dialog" aria-modal="true" aria-label="Campaign detail" tabIndex={-1} onClick={onClose} onKeyDown={(event) => { if (event.key === "Escape") onClose(); }}>
      <div className="h-full w-full max-w-3xl space-y-5 overflow-y-auto bg-background p-5 shadow-xl" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between"><h2 className="text-xl font-semibold">{query.data?.campaign.name ?? "Campaign"}</h2><Button size="icon" variant="ghost" aria-label="Close" onClick={onClose}><X /></Button></div>
        {query.isLoading ? <State /> : query.isError || !query.data ? <State error={query.error} retry={() => query.refetch()} /> : (
          <>
            <DetailSummary detail={query.data} />
            <div className="flex flex-wrap gap-2">{(["pause", "expire", "archive"] as const).filter((verb) => query.data.allowed_operations.includes(verb)).map((verb) => <Button key={verb} size="sm" variant="outline" className="capitalize" onClick={() => setAction(verb)}>{verb}</Button>)}</div>
            {action ? <ReasonDialog title={`${action[0].toUpperCase()}${action.slice(1)} campaign`} impact={impacts[action]} busy={transition.isPending} error={transition.error} onCancel={() => setAction(null)} onSubmit={(reason) => transition.mutate({ verb: action, reason })} /> : null}
            <EditCampaign detail={query.data} onSaved={invalidate} />
            <Rules detail={query.data} onSaved={invalidate} />
            <Codes detail={query.data} onSaved={invalidate} />
            <Block title="Audit history (latest 50)">{query.data.audit.length === 0 ? <p className="text-sm text-muted-foreground">No audit events.</p> : <ul className="divide-y text-sm">{query.data.audit.map((event) => <li key={event.id} className="py-2"><div className="flex flex-wrap justify-between gap-2"><span className="font-medium">{event.action}</span><span className="text-xs text-muted-foreground">{when(event.occurred_at)}</span></div><p className="text-xs text-muted-foreground">{event.actor_type}{event.actor_email ? ` · ${event.actor_email}` : ""}{typeof event.safe_metadata.reason === "string" ? ` · “${event.safe_metadata.reason}”` : ""}</p></li>)}</ul>}</Block>
          </>
        )}
      </div>
    </div>
  );
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return <section className="space-y-3 rounded-lg border bg-card p-4"><h3 className="text-sm font-semibold uppercase tracking-wide">{title}</h3>{children}</section>;
}

function DetailSummary({ detail }: { detail: CampaignDetail }) {
  const { campaign } = detail;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2"><Badge variant="outline">{campaign.status}</Badge><Badge variant="outline">Workspace: {detail.workspace.name}</Badge><Badge variant="outline">Authored by {campaign.origin}</Badge></div>
      <p className="rounded-md border border-pink-500/30 bg-pink-500/5 p-3 text-xs">Funding: discount borne by <strong>{detail.funding.discount_borne_by}</strong>. Platform-funded: {detail.funding.platform_funded ? "yes" : "no"}. Cross-Workspace redemption: {detail.funding.cross_workspace_redemption ? "yes" : "no"}. {detail.funding.note}</p>
      <dl className="grid gap-3 text-sm sm:grid-cols-3"><div><dt className="text-muted-foreground">Valid from</dt><dd>{when(campaign.valid_from)}</dd></div><div><dt className="text-muted-foreground">Valid until</dt><dd>{when(campaign.valid_until)}</dd></div><div><dt className="text-muted-foreground">Started</dt><dd>{when(campaign.started_at)}</dd></div></dl>
      <div className="grid gap-3 md:grid-cols-2">
        <Block title="Redemptions by status">{detail.redemptions.length === 0 ? <p className="text-sm text-muted-foreground">None yet.</p> : <ul className="text-sm">{detail.redemptions.map((row) => <li key={`${row.status}-${row.currency}`} className="flex justify-between"><span>{row.status} · {row.currency}</span><span>{row.count} · {row.currency} {row.discount_amount}</span></li>)}</ul>}</Block>
        <Block title="Confirmed booking value">{detail.confirmed_booking_value.length === 0 ? <p className="text-sm text-muted-foreground">No confirmed bookings.</p> : <ul className="text-sm">{detail.confirmed_booking_value.map((row) => <li key={row.currency}>{row.currency}: {row.bookings} bookings · gross {row.gross_amount} · discount granted {row.discount_granted} · net {row.net_amount}</li>)}</ul>}</Block>
      </div>
    </div>
  );
}

function EditCampaign({ detail, onSaved }: { detail: CampaignDetail; onSaved: () => void }) {
  const [name, setName] = useState(detail.campaign.name);
  const [description, setDescription] = useState(detail.campaign.description ?? "");
  const [reason, setReason] = useState("");
  const editable = new Set(detail.editable_fields);
  const save = useMutation({ mutationFn: () => service.updateCampaign(detail.campaign.id, { name: name.trim(), description: description.trim() || null, reason: reason.trim(), confirmed: true }), onSuccess: () => { setReason(""); onSaved(); } });
  if (!editable.has("name")) return null;
  return (
    <Block title="Edit details">
      <p className="text-xs text-muted-foreground">{editable.has("valid_from") ? "DRAFT: name, description and validity window are editable." : "Live campaigns: only name and description are editable; the validity window is locked."}</p>
      <div className="grid gap-3 md:grid-cols-2"><Input aria-label="Campaign name" value={name} maxLength={255} onChange={(event) => setName(event.target.value)} /><Input aria-label="Campaign description" value={description} maxLength={2000} onChange={(event) => setDescription(event.target.value)} /><Input aria-label="Reason" placeholder="Reason (audited)" className="md:col-span-2" value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} /></div>
      {save.isError ? <p className="text-sm text-destructive" role="alert">{errorText(save.error)}</p> : null}
      <Button size="sm" disabled={!name.trim() || reason.trim().length < 3 || save.isPending} onClick={() => save.mutate()}>Save details</Button>
    </Block>
  );
}

const MAX_TARGETS = 100;
const KIND_LABEL: Record<CatalogTargetKind, string> = { property: "Properties", room_type: "Room types", rate_plan: "Rate plans" };
type Selection = Record<CatalogTargetKind, Record<string, CatalogTarget>>;
const emptySelection = (): Selection => ({ property: {}, room_type: {}, rate_plan: {} });

/** Why a catalog row cannot sit under the parents already selected, if it cannot. */
function parentMismatch(item: CatalogTarget, selection: Selection): string | null {
  const properties = Object.keys(selection.property);
  const roomTypes = Object.keys(selection.room_type);
  if (item.kind === "room_type" && properties.length && !properties.includes(item.property_id ?? "")) return "not in a selected property";
  if (item.kind === "rate_plan") {
    if (roomTypes.length && !roomTypes.includes(item.room_type_id ?? "")) return "not in a selected room type";
    if (!roomTypes.length && properties.length && !properties.includes(item.property_id ?? "")) return "not in a selected property";
  }
  return null;
}

function TargetLabels({ ids, labels }: { ids: string[]; labels: CampaignDetail["target_labels"] }) {
  if (!ids.length) return <>all</>;
  return <>{ids.map((id) => labels[id] ? `${labels[id].name}${labels[id].active ? "" : " (inactive)"}` : "unknown").join(", ")}</>;
}

/** Paged, Workspace-scoped catalog picker. Reads are audited server-side once per admin, campaign and 15-minute window. */
function TargetPicker({ campaignId, kind, selection, onToggle }: { campaignId: string; kind: CatalogTargetKind; selection: Selection; onToggle: (item: CatalogTarget, on: boolean) => void }) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState<string | undefined>(undefined);
  const [showInactive, setShowInactive] = useState(false);
  // Debounced so typing does not write one audit event per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => { setTerm(search.trim().length >= 2 ? search.trim() : undefined); setPage(1); }, 400);
    return () => clearTimeout(timer);
  }, [search]);
  const properties = Object.keys(selection.property);
  const roomTypes = Object.keys(selection.room_type);
  const roomTypeFilter = kind === "rate_plan" && roomTypes.length === 1 ? roomTypes[0] : undefined;
  const propertyFilter = kind !== "property" && !roomTypeFilter && properties.length === 1 ? properties[0] : undefined;
  const query = useQuery({
    queryKey: ["platform-catalog", campaignId, kind, page, term, propertyFilter, roomTypeFilter, showInactive],
    queryFn: () => service.catalog(campaignId, { kind, page, page_size: 10, search: term, property_id: propertyFilter, room_type_id: roomTypeFilter, active_only: showInactive ? "false" : undefined }),
    staleTime: 60_000,
  });
  const chosen = Object.values(selection[kind]);
  const full = chosen.length >= MAX_TARGETS;
  return (
    <fieldset className="space-y-2 rounded-md border p-3 text-sm">
      <legend className="px-1 text-xs text-muted-foreground">{KIND_LABEL[kind]} (none = all · max {MAX_TARGETS})</legend>
      <div className="flex flex-wrap items-center gap-3">
        <Input aria-label={`Search ${KIND_LABEL[kind]}`} className="w-56" placeholder="Search name or code" value={search} onChange={(event) => setSearch(event.target.value)} />
        <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={showInactive} onChange={(event) => { setShowInactive(event.target.checked); setPage(1); }} />Show inactive</label>
      </div>
      {chosen.length ? <div className="flex flex-wrap gap-1">{chosen.map((item) => <Badge key={item.id} variant="muted" className="gap-1">{item.name}<button type="button" aria-label={`Remove ${item.name}`} onClick={() => onToggle(item, false)}><X className="size-3" /></button></Badge>)}</div> : null}
      {query.isLoading ? <State /> : query.isError || !query.data ? <State error={query.error} retry={() => query.refetch()} /> : (
        <>
          {query.data.items.length === 0 ? <p className="text-xs text-muted-foreground">No matching {KIND_LABEL[kind].toLowerCase()}.</p> : (
            <ul className="space-y-1">{query.data.items.map((item) => {
              const checked = Boolean(selection[kind][item.id]);
              const mismatch = parentMismatch(item, selection);
              return <li key={item.id}><label className="flex items-center gap-2"><input type="checkbox" checked={checked} disabled={!checked && (full || Boolean(mismatch))} onChange={(event) => onToggle(item, event.target.checked)} /><span>{item.name}</span>{item.code ? <span className="text-xs text-muted-foreground">{item.code}</span> : null}{item.currency && item.kind !== "room_type" ? <span className="text-xs text-muted-foreground">{item.currency}</span> : null}{item.active ? null : <Badge variant="outline">inactive</Badge>}{mismatch ? <span className="text-xs text-muted-foreground">· {mismatch}</span> : null}</label></li>;
            })}</ul>
          )}
          <Pager page={page} data={query.data} onPage={setPage} />
        </>
      )}
    </fieldset>
  );
}

function Rules({ detail, onSaved }: { detail: CampaignDetail; onSaved: () => void }) {
  const draft = detail.allowed_operations.includes("add_rule");
  const [form, setForm] = useState({ name: "", type: "PERCENTAGE", value: "", currency: "", max: "", minimum: "", total: "", perCustomer: "", sources: [] as string[], reason: "" });
  const [targeting, setTargeting] = useState(false);
  const [selection, setSelection] = useState<Selection>(emptySelection);
  const toggle = (item: CatalogTarget, on: boolean) => setSelection((value) => {
    const next = { ...value[item.kind] };
    if (on) next[item.id] = item; else delete next[item.id];
    return { ...value, [item.kind]: next };
  });
  const ids = (kind: CatalogTargetKind) => Object.keys(selection[kind]);
  const add = useMutation({
    mutationFn: () => service.addRule(detail.campaign.id, { name: form.name.trim(), discount_type: form.type, discount_value: form.value, currency: form.currency.trim().toUpperCase() || null, max_discount_amount: form.max || null, minimum_subtotal: form.minimum || null, total_usage_limit: form.total ? Number(form.total) : null, per_customer_limit: form.perCustomer ? Number(form.perCustomer) : null, property_ids: ids("property"), room_type_ids: ids("room_type"), rate_plan_ids: ids("rate_plan"), sources: form.sources, reason: form.reason.trim(), confirmed: true }),
    onSuccess: () => { setForm((value) => ({ ...value, name: "", value: "", reason: "" })); setSelection(emptySelection()); onSaved(); },
  });
  const valueError = form.value && (Number(form.value) <= 0 || (form.type === "PERCENTAGE" && Number(form.value) > 100)) ? "Percentage must be 0–100; amounts must be positive." : null;
  const currencyError = form.type === "FIXED_AMOUNT" && !/^[A-Za-z]{3}$/.test(form.currency) ? "Fixed amounts require a 3-letter currency." : null;
  const orphan = [...Object.values(selection.room_type), ...Object.values(selection.rate_plan)].find((item) => parentMismatch(item, selection));
  const targetError = orphan ? `${orphan.name} is ${parentMismatch(orphan, selection)}; the rule could never match. Remove it or adjust the parents.` : null;
  const addError = add.error instanceof ApiError && add.error.code === "PROMOTION_TARGET_INVALID" ? "A selected property, room type, or rate plan no longer belongs to this Workspace. Reload the catalog and try again." : add.isError ? errorText(add.error) : null;
  return (
    <Block title="Discount rules and eligibility">
      {detail.rules.length === 0 ? <p className="text-sm text-muted-foreground">No rules.</p> : <ul className="divide-y text-sm">{detail.rules.map((rule) => <li key={rule.id} className="py-2"><p className="font-medium">{rule.name} · {rule.discount_type === "PERCENTAGE" ? `${rule.discount_value}%` : `${rule.currency} ${rule.discount_value}`}{rule.max_discount_amount ? ` (cap ${rule.max_discount_amount})` : ""}</p><p className="text-xs text-muted-foreground">Min subtotal {rule.minimum_subtotal ?? "—"} · total limit {rule.total_usage_limit ?? "∞"} · per customer {rule.per_customer_limit ?? "∞"} · sources {rule.eligibility.sources.join(", ") || "all"}</p><p className="text-xs text-muted-foreground">Properties <TargetLabels ids={rule.eligibility.property_ids} labels={detail.target_labels} /> · room types <TargetLabels ids={rule.eligibility.room_type_ids} labels={detail.target_labels} /> · rate plans <TargetLabels ids={rule.eligibility.rate_plan_ids} labels={detail.target_labels} /></p></li>)}</ul>}
      {draft ? (
        <div className="space-y-3 border-t pt-3">
          <p className="text-xs text-muted-foreground">Add a rule while the campaign is DRAFT. Catalog targets come from {detail.workspace.name} only; the Workspace still decides activation and funds the discount.</p>
          <div className="grid gap-3 md:grid-cols-3">
            <Input aria-label="Rule name" placeholder="Rule name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
            <select aria-label="Discount type" className={selectClass} value={form.type} onChange={(event) => setForm({ ...form, type: event.target.value })}><option value="PERCENTAGE">Percentage</option><option value="FIXED_AMOUNT">Fixed amount</option></select>
            <Input aria-label="Discount value" placeholder="Value" inputMode="decimal" value={form.value} onChange={(event) => setForm({ ...form, value: event.target.value })} />
            <Input aria-label="Currency" placeholder="Currency (e.g. THB)" maxLength={3} value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value })} />
            <Input aria-label="Maximum discount" placeholder="Max discount" inputMode="decimal" value={form.max} onChange={(event) => setForm({ ...form, max: event.target.value })} />
            <Input aria-label="Minimum subtotal" placeholder="Minimum subtotal" inputMode="decimal" value={form.minimum} onChange={(event) => setForm({ ...form, minimum: event.target.value })} />
            <Input aria-label="Total usage limit" placeholder="Total usage limit" inputMode="numeric" value={form.total} onChange={(event) => setForm({ ...form, total: event.target.value })} />
            <Input aria-label="Per-customer limit" placeholder="Per-customer limit" inputMode="numeric" value={form.perCustomer} onChange={(event) => setForm({ ...form, perCustomer: event.target.value })} />
            <Input aria-label="Reason" placeholder="Reason (audited)" value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} />
          </div>
          <fieldset className="flex flex-wrap gap-3 text-sm"><legend className="mb-1 text-xs text-muted-foreground">Sources (none = all)</legend>{SOURCES.map((source) => <label key={source} className="flex items-center gap-1"><input type="checkbox" checked={form.sources.includes(source)} onChange={(event) => setForm({ ...form, sources: event.target.checked ? [...form.sources, source] : form.sources.filter((item) => item !== source) })} />{source}</label>)}</fieldset>
          {targeting ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between"><p className="text-xs font-medium">Catalog targeting</p><Button size="sm" variant="ghost" onClick={() => { setTargeting(false); setSelection(emptySelection()); }}>Clear and close</Button></div>
              {(["property", "room_type", "rate_plan"] as const).map((kind) => <TargetPicker key={kind} campaignId={detail.campaign.id} kind={kind} selection={selection} onToggle={toggle} />)}
            </div>
          ) : detail.workspace.status === "ACTIVE" ? <Button size="sm" variant="outline" onClick={() => setTargeting(true)}>Target specific properties, room types, or rate plans</Button> : <p className="text-xs text-muted-foreground">Catalog targeting is unavailable while {detail.workspace.name} is {detail.workspace.status}.</p>}
          {valueError || currencyError || targetError ? <p className="text-xs text-destructive">{valueError ?? currencyError ?? targetError}</p> : null}
          {addError ? <p className="text-sm text-destructive" role="alert">{addError}</p> : null}
          <Button size="sm" disabled={!form.name.trim() || !form.value || Boolean(valueError || currencyError || targetError) || form.reason.trim().length < 3 || add.isPending} onClick={() => add.mutate()}>Add rule</Button>
        </div>
      ) : null}
    </Block>
  );
}

function Codes({ detail, onSaved }: { detail: CampaignDetail; onSaved: () => void }) {
  const draft = detail.allowed_operations.includes("add_code");
  const [code, setCode] = useState("");
  const [rule, setRule] = useState("");
  const [limit, setLimit] = useState("");
  const [reason, setReason] = useState("");
  const add = useMutation({ mutationFn: () => service.addCode(detail.campaign.id, { promotion_id: rule, code: code.trim(), usage_limit: limit ? Number(limit) : null, reason: reason.trim(), confirmed: true }), onSuccess: () => { setCode(""); setReason(""); onSaved(); } });
  const codeError = code && !/^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$/.test(code.trim()) ? "Use 1–32 letters, digits, - or _." : null;
  return (
    <Block title="Codes">
      {detail.codes.length === 0 ? <p className="text-sm text-muted-foreground">No codes.</p> : <CodeTable items={detail.codes} onSaved={onSaved} />}
      {draft && detail.rules.length ? (
        <div className="grid gap-3 border-t pt-3 md:grid-cols-4">
          <select aria-label="Rule" className={selectClass} value={rule} onChange={(event) => setRule(event.target.value)}><option value="">Rule…</option>{detail.rules.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
          <Input aria-label="Code" placeholder="CODE" className="uppercase" maxLength={32} value={code} onChange={(event) => setCode(event.target.value)} />
          <Input aria-label="Usage limit" placeholder="Usage limit" inputMode="numeric" value={limit} onChange={(event) => setLimit(event.target.value)} />
          <Input aria-label="Reason" placeholder="Reason (audited)" value={reason} onChange={(event) => setReason(event.target.value)} />
          {codeError ? <p className="text-xs text-destructive md:col-span-4">{codeError}</p> : null}
          {add.isError ? <p className="text-sm text-destructive md:col-span-4" role="alert">{errorText(add.error)}</p> : null}
          <Button size="sm" className="md:col-span-1" disabled={!rule || !code.trim() || Boolean(codeError) || reason.trim().length < 3 || add.isPending} onClick={() => add.mutate()}>Add code</Button>
        </div>
      ) : null}
    </Block>
  );
}

function CodeTable({ items, onSaved }: { items: CodeListItem[]; onSaved: () => void }) {
  const [pending, setPending] = useState<{ id: string; verb: "disable" | "archive" } | null>(null);
  const mutate = useMutation({ mutationFn: ({ id, verb, reason }: { id: string; verb: "disable" | "archive"; reason: string }) => service.transitionCode(id, verb, reason), onSuccess: () => { setPending(null); onSaved(); } });
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto"><table className="w-full min-w-[640px] text-left text-sm"><thead className="border-b"><tr><th className="p-2">Code</th><th className="p-2">Status</th><th className="p-2">Discount</th><th className="p-2">Used / limit</th><th className="p-2">Remaining</th><th className="p-2"><span className="sr-only">Actions</span></th></tr></thead><tbody>{items.map((item) => (
        <tr key={item.id} className="border-b last:border-0"><td className="p-2 font-mono font-semibold">{item.code}</td><td className="p-2"><Badge variant="outline">{item.status}</Badge></td><td className="p-2">{item.discount.type === "PERCENTAGE" ? `${item.discount.value}%` : `${item.discount.currency} ${item.discount.value}`}</td><td className="p-2">{item.counted_uses} / {item.effective_limit ?? "∞"}</td><td className="p-2">{item.remaining ?? "∞"}</td><td className="p-2 text-right">{item.status === "ACTIVE" ? <Button size="sm" variant="outline" onClick={() => setPending({ id: item.id, verb: "disable" })}>Disable</Button> : null}{item.status !== "ARCHIVED" ? <Button size="sm" variant="ghost" onClick={() => setPending({ id: item.id, verb: "archive" })}>Archive</Button> : null}</td></tr>
      ))}</tbody></table></div>
      {pending ? <ReasonDialog title={`${pending.verb === "disable" ? "Disable" : "Archive"} code`} impact="Affects future validations and Holds only. Re-enabling is reserved for the owning Workspace." busy={mutate.isPending} error={mutate.error} onCancel={() => setPending(null)} onSubmit={(reason) => mutate.mutate({ ...pending, reason })} /> : null}
    </div>
  );
}

function CodeList() {
  const invalidate = useInvalidate();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const term = search.trim() || undefined;
  const query = useQuery({ queryKey: ["platform-marketing", "codes", page, term, status], queryFn: () => service.codes({ page, page_size: 25, search: term, status }) });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3"><div className="space-y-1.5"><Label htmlFor="code-search">Code prefix</Label><Input id="code-search" className="w-56 uppercase" maxLength={32} value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></div><div className="space-y-1.5"><Label htmlFor="code-status">Status</Label><select id="code-status" className={selectClass} value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">All</option>{CODE_STATUSES.map((item) => <option key={item}>{item}</option>)}</select></div></div>
      {query.isLoading ? <State /> : query.isError || !query.data ? <State error={query.error} retry={() => query.refetch()} /> : (
        <>
          <div className="rounded-lg border bg-card p-3">{query.data.items.length === 0 ? <p className="p-8 text-center text-sm text-muted-foreground">No codes match this view.</p> : <><p className="mb-2 text-xs text-muted-foreground">Workspace · campaign shown per code below.</p><ul className="mb-3 space-y-1 text-xs text-muted-foreground">{query.data.items.map((item) => <li key={item.id}><span className="font-mono text-foreground">{item.code}</span> — {item.workspace} · {item.campaign.name} ({item.campaign.status})</li>)}</ul><CodeTable items={query.data.items} onSaved={invalidate} /></>}</div>
          <Pager page={page} data={query.data} onPage={setPage} />
        </>
      )}
    </div>
  );
}

const RANGES = { "30": "Last 30 days", "90": "Last 90 days", "365": "Last 365 days" } as const;

function Analytics() {
  const [days, setDays] = useState<keyof typeof RANGES>("30");
  const [end] = useState(() => new Date().toISOString());
  const start = new Date(new Date(end).getTime() - Number(days) * 86_400_000).toISOString();
  const query = useQuery({ queryKey: ["platform-marketing", "analytics", start, end], queryFn: () => service.analytics(start, end) });
  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3"><div className="space-y-1.5"><Label htmlFor="range">Range (UTC)</Label><select id="range" className={selectClass} value={days} onChange={(event) => setDays(event.target.value as keyof typeof RANGES)}>{Object.entries(RANGES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div></div>
      {query.isLoading ? <State /> : query.isError || !query.data ? <State error={query.error} retry={() => query.refetch()} /> : <AnalyticsBody data={query.data} />}
    </div>
  );
}

function Stat({ label, value, tone = "cyan" }: { label: string; value: ReactNode; tone?: "cyan" | "pink" }) {
  return <article className={`rounded-lg border bg-card p-4 ${tone === "pink" ? "border-pink-500/30" : "border-cyan-500/20"}`}><p className="text-2xl font-semibold">{value}</p><p className="mt-1 text-xs text-muted-foreground">{label}</p></article>;
}

function AnalyticsBody({ data }: { data: CampaignAnalytics }) {
  const lifecycle = data.lifecycle;
  const maxDay = Math.max(1, ...data.daily_trend.map((row) => row.redemptions));
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Reserved at Hold (in range)" value={data.reservation_funnel.reserved} />
        <Stat label="Confirmed redemptions" value={data.reservation_funnel.confirmed} />
        <Stat label="Released / lapsed" value={data.reservation_funnel.released} tone="pink" />
        <Stat label="Active reservations now" value={data.reservation_funnel.active_reservations} />
      </div>
      <p className="text-xs text-muted-foreground">{data.reservation_funnel.definition} {data.definition}</p>
      <div className="grid gap-4 lg:grid-cols-2">
        <Block title="Confirmed value by currency">{data.confirmed_by_currency.length === 0 ? <p className="text-sm text-muted-foreground">No confirmed redemptions in range.</p> : <table className="w-full text-sm"><thead><tr className="text-left text-muted-foreground"><th>Currency</th><th>Uses</th><th>Gross</th><th>Discount granted</th><th>Net</th></tr></thead><tbody>{data.confirmed_by_currency.map((row) => <tr key={row.currency}><td>{row.currency}</td><td>{row.redemptions}</td><td>{row.gross_amount}</td><td>{row.discount_granted}</td><td>{row.net_amount}</td></tr>)}</tbody></table>}<p className="text-xs text-muted-foreground">Discount granted is hotel revenue forgone by the owning Workspace — not platform campaign cost. {data.campaign_cost.reason}</p></Block>
        <Block title="Scheduled lifecycle processing"><div className="flex flex-wrap gap-2"><Badge variant="outline" className={lifecycle.health === "HEALTHY" ? "border-cyan-500 text-cyan-600" : "border-pink-500 text-pink-600"}>{lifecycle.health}</Badge>{lifecycle.alerts.map((alert) => <Badge key={alert} variant="outline">{alert}</Badge>)}</div><dl className="grid grid-cols-2 gap-2 text-sm"><dt className="text-muted-foreground">Last success</dt><dd>{when(lifecycle.last_succeeded_at)}</dd><dt className="text-muted-foreground">Last failure</dt><dd>{when(lifecycle.last_failed_at)}{lifecycle.last_error_code ? ` · ${lifecycle.last_error_code}` : ""}</dd><dt className="text-muted-foreground">Runs / failures</dt><dd>{lifecycle.total_runs} / {lifecycle.total_failures}</dd><dt className="text-muted-foreground">Transitions applied</dt><dd>{lifecycle.total_processed}</dd><dt className="text-muted-foreground">Overdue expiry / start</dt><dd>{lifecycle.overdue_expiry} / {lifecycle.overdue_start}</dd></dl></Block>
      </div>
      <Block title="Confirmed redemptions by day (UTC)">{data.daily_trend.length === 0 ? <p className="text-sm text-muted-foreground">No data in range.</p> : <ul className="space-y-1 text-xs">{data.daily_trend.map((row) => <li key={`${row.date}-${row.currency}`} className="grid grid-cols-[100px_1fr_160px] items-center gap-2"><span>{row.date}</span><span className="h-2 rounded bg-cyan-500" style={{ width: `${(row.redemptions / maxDay) * 100}%` }} aria-hidden /><span className="text-right">{row.redemptions} · {row.currency} {row.discount_granted}</span></li>)}</ul>}</Block>
      <div className="grid gap-4 lg:grid-cols-3">
        <Block title="Campaigns by status"><ul className="text-sm">{Object.entries(data.campaigns_by_status).map(([key, value]) => <li key={key} className="flex justify-between"><span>{key}</span><span>{value}</span></li>)}</ul><p className="text-xs text-muted-foreground">Authored: {Object.entries(data.campaigns_by_origin).map(([key, value]) => `${key} ${value}`).join(" · ")}</p></Block>
        <Block title="Codes by status"><ul className="text-sm">{Object.entries(data.codes_by_status).map(([key, value]) => <li key={key} className="flex justify-between"><span>{key}</span><span>{value}</span></li>)}</ul></Block>
        <Block title="By source / channel">{data.by_source.length === 0 ? <p className="text-sm text-muted-foreground">No data.</p> : <ul className="text-sm">{data.by_source.map((row) => <li key={`${row.source}-${row.currency}`} className="flex justify-between"><span>{row.source}</span><span>{row.redemptions} · {row.currency} {row.discount_granted}</span></li>)}</ul>}</Block>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Block title="Top Workspaces">{data.top_workspaces.length === 0 ? <p className="text-sm text-muted-foreground">No data.</p> : <ul className="text-sm">{data.top_workspaces.map((row) => <li key={`${row.workspace_id}-${row.currency}`} className="flex justify-between"><span>{row.workspace}</span><span>{row.redemptions} · {row.currency} {row.discount_granted}</span></li>)}</ul>}</Block>
        <Block title="Top campaigns">{data.top_campaigns.length === 0 ? <p className="text-sm text-muted-foreground">No data.</p> : <ul className="text-sm">{data.top_campaigns.map((row) => <li key={`${row.campaign_id}-${row.currency}`} className="flex justify-between"><span>{row.campaign} <span className="text-muted-foreground">({row.workspace})</span></span><span>{row.redemptions} · {row.currency} {row.discount_granted}</span></li>)}</ul>}</Block>
      </div>
      <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">Not available: code validation attempts ({data.validations.reason}) and ROI / acquisition cost.</p>
    </div>
  );
}
