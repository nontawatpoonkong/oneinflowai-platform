"use client";

import Link from "next/link";
import { AlertTriangle, Loader2, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/hooks/use-auth";
import { useMyWorkspace, useWorkspaceMembers } from "@/hooks/api/use-workspace";

export function WorkspaceView(){
  const t=useTranslations("operations.workspace"); const workspace=useMyWorkspace(); const members=useWorkspaceMembers(workspace.data?.id); const {user}=useAuth();
  if(workspace.isLoading||members.isLoading)return <State icon={Loader2} text={t("loading")} spin/>;
  if(workspace.isError||members.isError)return <State icon={AlertTriangle} text={t("error")} action={()=>{void workspace.refetch();void members.refetch();}}/>;
  const current=members.data?.find((member)=>member.user_id===user?.id);
  return <div className="space-y-6"><header><h1 className="text-2xl font-semibold">{t("title")}</h1><p className="text-sm text-muted-foreground">{t("description")}</p></header><section className="rounded-lg border bg-card p-5"><p className="text-xs text-muted-foreground">{t("workspaceName")}</p><div className="mt-1 flex flex-wrap items-center gap-2"><h2 className="text-xl font-semibold">{workspace.data?.name}</h2>{current?<Badge variant="muted">{t(`roles.${current.role}`)}</Badge>:null}</div><p className="mt-2 text-sm text-muted-foreground">{t("roleNotice")}</p><Link href="/dashboard/integrations" className="mt-4 inline-block text-sm font-medium text-primary">{t("manageChannels")}</Link></section><section><h2 className="mb-3 flex items-center gap-2 text-lg font-semibold"><Users className="size-5"/>{t("members")}</h2><div className="overflow-x-auto rounded-lg border bg-card"><table className="w-full text-left text-sm"><thead className="border-b bg-muted/40"><tr><th className="p-3">{t("name")}</th><th className="p-3">{t("email")}</th><th className="p-3">{t("role")}</th></tr></thead><tbody>{members.data?.map((member)=><tr key={member.id} className="border-b last:border-0"><td className="p-3">{member.full_name||"—"}</td><td className="p-3">{member.email}</td><td className="p-3"><Badge variant="outline">{t(`roles.${member.role}`)}</Badge></td></tr>)}</tbody></table></div></section></div>;
}
function State({icon:Icon,text,action,spin}:{icon:typeof Users;text:string;action?:()=>unknown;spin?:boolean}){const common=useTranslations("common");return <div className="grid min-h-64 place-items-center rounded-lg border border-dashed p-8 text-center"><div><Icon className={`mx-auto mb-3 size-8 text-muted-foreground ${spin?"animate-spin":""}`}/><p>{text}</p>{action?<Button className="mt-3" variant="outline" onClick={action}>{common("tryAgain")}</Button>:null}</div></div>}
