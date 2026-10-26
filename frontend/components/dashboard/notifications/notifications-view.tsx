"use client";

import Link from "next/link";
import { AlertTriangle, Bell, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { useNotificationActions, useNotifications } from "@/hooks/api/use-notifications";
import type { NotificationDTO } from "@/types/notification";

const href = (item: NotificationDTO) => item.entity_type === "CONVERSATION" ? `/dashboard/inbox?conversation=${item.entity_id}` : item.entity_type === "ACTION" ? `/dashboard/actions?action=${item.entity_id}` : `/dashboard/payments?payment=${item.entity_id}`;

export function NotificationsView() {
  const t = useTranslations("operations.notifications"); const common = useTranslations("common");
  const query = useNotifications(); const actions = useNotificationActions();
  return <div className="space-y-6"><header className="flex flex-wrap items-end justify-between gap-3"><div><h1 className="text-2xl font-semibold">{t("title")}</h1><p className="text-sm text-muted-foreground">{t("description")}</p></div>{query.data?.unread_count ? <Button variant="outline" onClick={() => actions.markAllRead.mutate()}>{t("markAllRead")}</Button> : null}</header>
    {query.isLoading ? <State icon={Loader2} text={common("loading")} spin /> : query.isError ? <State icon={AlertTriangle} text={t("error")} action={() => query.refetch()} /> : !query.data?.items.length ? <State icon={Bell} text={t("empty")} /> : <ul className="divide-y rounded-lg border bg-card">{query.data.items.map((item) => <li key={item.id} className={`p-4 ${item.is_read ? "opacity-70" : "bg-brand/5"}`}><Link href={href(item)} onClick={() => !item.is_read && actions.markRead.mutate(item.id)} className="block"><div className="flex justify-between gap-4"><div><p className="font-medium">{item.title}</p><p className="mt-1 text-sm text-muted-foreground">{item.body}</p></div>{!item.is_read ? <span className="mt-1 size-2 shrink-0 rounded-full bg-brand" /> : null}</div><p className="mt-2 text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString()}</p></Link></li>)}</ul>}
  </div>;
}
function State({icon:Icon,text,action,spin}:{icon:typeof Bell;text:string;action?:()=>unknown;spin?:boolean}) { const common=useTranslations("common"); return <div className="grid min-h-64 place-items-center rounded-lg border border-dashed p-8 text-center"><div><Icon className={`mx-auto mb-3 size-8 text-muted-foreground ${spin?"animate-spin":""}`}/><p className="text-sm text-muted-foreground">{text}</p>{action?<Button className="mt-3" variant="outline" onClick={action}>{common("tryAgain")}</Button>:null}</div></div>; }
