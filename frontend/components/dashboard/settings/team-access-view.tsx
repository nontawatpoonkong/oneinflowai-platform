"use client";

import { Copy, KeyRound, ShieldCheck, Trash2, UserCheck, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  useMyWorkspace,
  useWorkspaceAccess,
  useWorkspaceAccessRequests,
  useWorkspaceJoinSettings,
  useWorkspaceMembers,
} from "@/hooks/api/use-workspace";
import { PERMISSION_GROUPS, PERMISSION_PRESETS } from "@/lib/workspace-permissions";
import { workspaceService } from "@/services/workspace/workspace.service";
import type { WorkspaceAccessRequestDTO, WorkspaceMemberDTO } from "@/types/api";

function CapabilityEditor({ value, onChange }: { value: string[]; onChange: (value: string[]) => void }) {
  const t = useTranslations("teamAccess");
  const selected = useMemo(() => new Set(value), [value]);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {Object.keys(PERMISSION_PRESETS).map((key) => (
          <Button key={key} type="button" size="sm" variant="outline" onClick={() => onChange(PERMISSION_PRESETS[key])}>
            {t(`presets.${key}`)}
          </Button>
        ))}
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        {PERMISSION_GROUPS.map((group) => (
          <section key={group.key} className="rounded-xl border p-4">
            <h4 className="text-sm font-semibold">{t(`groups.${group.key}`)}</h4>
            <div className="mt-3 grid gap-2">
              {group.capabilities.map((capability) => (
                <Checkbox
                  key={capability}
                  id={`capability-${capability}`}
                  checked={selected.has(capability)}
                  onCheckedChange={(checked) => {
                    const next = new Set(selected);
                    if (checked) next.add(capability); else next.delete(capability);
                    onChange([...next]);
                  }}
                  label={t(`capabilities.${capability}`)}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

export function TeamAccessView() {
  const t = useTranslations("teamAccess");
  const { data: workspace } = useMyWorkspace();
  const access = useWorkspaceAccess(workspace?.id);
  const members = useWorkspaceMembers(workspace?.id);
  const requests = useWorkspaceAccessRequests(workspace?.id);
  const joinSettings = useWorkspaceJoinSettings(workspace?.id);
  const [joinCode, setJoinCode] = useState<string | null>(null);
  const [selectedMember, setSelectedMember] = useState<WorkspaceMemberDTO | null>(null);
  const [selectedRequest, setSelectedRequest] = useState<WorkspaceAccessRequestDTO | null>(null);
  const [selectedRole, setSelectedRole] = useState<"admin" | "member">("member");
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const canManage = access.data?.capabilities.includes("workspace.members.manage") ?? false;
  const isOwner = access.data?.role === "owner";

  async function regenerateCode() {
    if (!workspace) return;
    const data = await workspaceService.regenerateJoinCode(workspace.id);
    setJoinCode(data.join_code ?? null);
    await joinSettings.refetch();
    toast.success(t("joinCodeGenerated"));
  }

  async function toggleJoinRequests() {
    if (!workspace) return;
    const enabled = !(joinSettings.data?.join_enabled ?? false);
    await workspaceService.setJoinEnabled(workspace.id, enabled);
    await joinSettings.refetch();
    toast.success(t(enabled ? "joinRequestsEnabled" : "joinRequestsDisabled"));
  }

  async function approveRequest() {
    if (!workspace || !selectedRequest) return;
    await workspaceService.approveAccessRequest(workspace.id, selectedRequest.id, {
      role: selectedRole,
      capabilities: selectedRole === "member" ? capabilities : [],
    });
    setSelectedRequest(null);
    setSelectedRole("member");
    setCapabilities([]);
    await Promise.all([requests.refetch(), members.refetch()]);
    toast.success(t("approved"));
  }

  async function saveMember() {
    if (!workspace || !selectedMember) return;
    if (selectedMember.role !== selectedRole) {
      await workspaceService.updateMemberRole(workspace.id, selectedMember.id, selectedRole);
    }
    if (selectedRole === "member") {
      await workspaceService.updateMemberCapabilities(workspace.id, selectedMember.id, capabilities);
    }
    setSelectedMember(null);
    setSelectedRole("member");
    await members.refetch();
    toast.success(t("saved"));
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("description")} />

      {canManage ? (
        <Card className="border-cyan-400/30">
          <CardHeader><CardTitle className="flex items-center gap-2"><KeyRound className="size-5 text-cyan-500" />{t("joinCodeTitle")}</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="flex-1">
              <p className="text-sm text-muted-foreground">{t("joinCodeDescription")}</p>
              <p className="mt-1 text-xs font-medium text-muted-foreground">
                {joinSettings.data?.join_enabled ? t("joinRequestsOn") : t("joinRequestsOff")}
                {joinSettings.data?.code_hint ? ` · ${t("codeHint")}: ${joinSettings.data.code_hint}` : ""}
              </p>
            </div>
            {joinCode ? <code className="rounded-lg bg-muted px-3 py-2 text-sm font-semibold tracking-wider">{joinCode}</code> : null}
            {joinCode ? <Button variant="outline" size="icon" aria-label={t("copy")} onClick={() => { navigator.clipboard.writeText(joinCode); toast.success(t("copied")); }}><Copy className="size-4" /></Button> : null}
            <Button
              variant="outline"
              onClick={toggleJoinRequests}
              disabled={joinSettings.isLoading || (!joinSettings.data?.join_enabled && !joinSettings.data?.code_hint)}
            >
              {joinSettings.data?.join_enabled ? t("disableJoinRequests") : t("enableJoinRequests")}
            </Button>
            <Button onClick={regenerateCode}>{t("regenerate")}</Button>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Users className="size-5" />{t("members")}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {members.isLoading ? <p className="text-sm text-muted-foreground">{t("loading")}</p> : null}
            {members.data?.map((member) => (
              <div key={member.id} className="flex flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1"><p className="truncate font-medium">{member.full_name || member.email}</p><p className="truncate text-sm text-muted-foreground">{member.email} · {t(`roles.${member.role}`)}</p></div>
                {canManage && member.role !== "owner" && (member.role === "member" || isOwner) ? <Button variant="outline" onClick={() => { setSelectedMember(member); setSelectedRole(member.role === "admin" ? "admin" : "member"); setCapabilities(member.capabilities.filter((item) => item !== "dashboard.view")); }}>{t("editAccess")}</Button> : <ShieldCheck className="size-5 text-cyan-500" />}
                {canManage && member.role !== "owner" && (member.role === "member" || isOwner) ? <Button variant="ghost" size="icon" aria-label={t("remove")} onClick={async () => { if (!workspace) return; await workspaceService.removeMember(workspace.id, member.id); await members.refetch(); }}><Trash2 className="size-4 text-destructive" /></Button> : null}
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="border-pink-400/20">
          <CardHeader><CardTitle className="flex items-center gap-2"><UserCheck className="size-5 text-pink-500" />{t("requests")}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {requests.data?.filter((item) => item.status === "PENDING").map((item) => (
              <div key={item.id} className="rounded-xl border p-4">
                <p className="font-medium">{item.full_name || item.email}</p><p className="text-sm text-muted-foreground">{item.email}</p>
                {item.message ? <p className="mt-2 text-sm">{item.message}</p> : null}
                {canManage ? <div className="mt-3 flex gap-2"><Button size="sm" onClick={() => { setSelectedRequest(item); setSelectedRole("member"); setCapabilities([]); }}>{t("review")}</Button><Button size="sm" variant="outline" onClick={async () => { if (!workspace) return; await workspaceService.rejectAccessRequest(workspace.id, item.id); await requests.refetch(); }}>{t("reject")}</Button></div> : null}
              </div>
            ))}
            {!requests.isLoading && !requests.data?.some((item) => item.status === "PENDING") ? <p className="text-sm text-muted-foreground">{t("noRequests")}</p> : null}
          </CardContent>
        </Card>
      </div>

      {selectedMember || selectedRequest ? (
        <Card className="border-cyan-400/30">
          <CardHeader><CardTitle>{selectedRequest ? t("approveAccess") : t("editAccess")}</CardTitle></CardHeader>
          <CardContent className="space-y-5">
            <label className="grid gap-2 text-sm font-medium">
              {t("roleLabel")}
              <select
                className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                value={selectedRole}
                onChange={(event) => setSelectedRole(event.target.value as "admin" | "member")}
              >
                <option value="member">{t("roles.member")}</option>
                {isOwner ? <option value="admin">{t("roles.admin")}</option> : null}
              </select>
            </label>
            {selectedRole === "member" ? <CapabilityEditor value={capabilities} onChange={setCapabilities} /> : (
              <p className="rounded-xl border border-cyan-400/30 bg-cyan-400/5 p-4 text-sm text-muted-foreground">{t("adminBaselineNotice")}</p>
            )}
            <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => { setSelectedMember(null); setSelectedRequest(null); setSelectedRole("member"); }}>{t("cancel")}</Button><Button onClick={selectedRequest ? approveRequest : saveMember}>{selectedRequest ? t("approve") : t("save")}</Button></div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
