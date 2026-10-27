"use client";

import {
  ArrowLeft,
  Facebook,
  Globe,
  MessageCircle,
  MessagesSquare,
  Send,
  UserRound,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { ConversationModeToggle } from "@/components/dashboard/inbox/conversation-mode-toggle";
import { StatusBadge } from "@/components/dashboard/shared/status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useConversationOperations } from "@/hooks/api/use-conversation-operations";
import { useConversations } from "@/hooks/api/use-conversations";
import { useMessages } from "@/hooks/api/use-messages";
import { useSendMessage } from "@/hooks/api/use-send-message";
import { useUpdateConversation } from "@/hooks/api/use-update-conversation";
import { useWorkspaceMembers } from "@/hooks/api/use-workspace";
import { cn } from "@/lib/utils";
import type { ConversationAiModeDTO, ConversationDTO } from "@/types/api";
import type { MessageDTO } from "@/types/message";

const terminalDelivery = { PENDING: "pending", SENT: "sent", FAILED: "failed" } as const;
const channelIcon = { line: MessageCircle, facebook: Facebook, web: Globe } as const;

function ChannelBadge({ channel }: { channel: ConversationDTO["channel"] }) {
  const t = useTranslations("inbox.channels");
  const safe = channel === "line" || channel === "facebook" ? channel : "web";
  const Icon = channelIcon[safe];
  return <Badge variant="muted" className="rounded-md px-2 py-1"><Icon className="size-3" />{t(safe)}</Badge>;
}

function MessageBubble({ message }: { message: MessageDTO }) {
  const t = useTranslations("inbox.delivery");
  const customer = message.sender_type === "customer";
  if (message.sender_type === "system") {
    return <div className="mx-auto max-w-xl rounded-md bg-muted px-3 py-2 text-center text-xs text-muted-foreground">{message.content}</div>;
  }
  return (
    <div className={cn("flex", customer ? "justify-start" : "justify-end")}>
      <div className={cn("max-w-[88%] rounded-md border px-3.5 py-2.5 text-sm sm:max-w-[72%]", customer ? "rounded-bl-sm bg-card" : message.sender_type === "agent" ? "rounded-br-sm border-brand bg-brand text-brand-foreground" : "rounded-br-sm border-brand/20 bg-brand-soft")}>
        <p className="whitespace-pre-wrap leading-6">{message.content}</p>
        <div className="mt-1.5 flex items-center justify-end gap-2 text-[10px] opacity-70">
          <span>{new Date(message.created_at).toLocaleString()}</span>
          {message.delivery ? <span className={message.delivery.status === "FAILED" ? "text-destructive" : ""}>{t(terminalDelivery[message.delivery.status])}</span> : null}
        </div>
      </div>
    </div>
  );
}

function Chat({ conversation, onBack }: { conversation: ConversationDTO | null; onBack: () => void }) {
  const t = useTranslations("inbox");
  const common = useTranslations("common");
  const [draft, setDraft] = useState("");
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messages = useMessages(conversation?.id ?? null, { page: 1, page_size: 100 });
  const send = useSendMessage(conversation?.id ?? null);
  const update = useUpdateConversation(conversation?.id ?? null);
  const ops = useConversationOperations(conversation?.id ?? null);
  const members = useWorkspaceMembers(conversation?.workspace_id);
  const markRead = ops.markRead;
  const modePending = ops.handoff.isPending || ops.returnToAi.isPending || update.isPending;

  useEffect(() => {
    if (conversation?.unread_count) markRead.mutate();
  }, [conversation?.id, conversation?.unread_count, markRead]);

  if (!conversation) {
    return <div className="grid h-full place-items-center"><EmptyState icon={MessagesSquare} title={t("empty.title")} description={t("empty.desc")} className="border-0" /></div>;
  }

  const scrollToLatest = () => window.requestAnimationFrame(() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }));
  const submit = () => {
    const content = draft.trim();
    if (!content || send.isPending) return;
    scrollToLatest();
    send.mutate(content, {
      onSuccess: (message) => {
        setDraft("");
        scrollToLatest();
        window.requestAnimationFrame(() => composerRef.current?.focus());
        if (message.delivery?.status === "FAILED") toast.error(t("deliveryFailed"));
      },
      onError: () => toast.error(t("sendFailed")),
    });
  };
  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    submit();
  };
  const changeMode = (mode: ConversationAiModeDTO) => {
    const onError = () => toast.error(t("modeChangeFailed"));
    if (mode === "HUMAN") return void ops.handoff.mutate(undefined, { onError });
    if (mode === "AUTO") return void ops.returnToAi.mutate(undefined, { onError });
    update.mutate(mode, { onError });
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-card">
      <header className="border-b border-border p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Button className="lg:hidden" size="icon" variant="ghost" onClick={onBack} aria-label={t("backToList")}><ArrowLeft /></Button>
          <div className="mr-auto min-w-0"><p className="truncate font-medium">{conversation.subject || conversation.customer_id}</p><ChannelBadge channel={conversation.channel} /></div>
          <Button size="sm" variant="outline" onClick={() => ops.assign.mutate(undefined)}>{t("assignToMe")}</Button>
          <select value={conversation.assigned_user_id ?? ""} onChange={(event) => event.target.value && ops.assign.mutate(event.target.value)} className="h-8 rounded-md border bg-background px-2 text-xs" aria-label={t("assignMember")}>
            <option value="">{t("assignMember")}</option>
            {members.data?.map((member) => <option key={member.user_id} value={member.user_id}>{member.full_name || member.email}</option>)}
          </select>
          <ConversationModeToggle activeMode={conversation.ai_mode} disabled={modePending} label={t("mode")} labels={{ AUTO: t("modes.auto"), COPILOT: t("modes.copilot"), HUMAN: t("modes.human") }} onSelect={changeMode} />
        </div>
      </header>
      <main className="flex-1 space-y-3 overflow-y-auto bg-surface/60 p-4">
        {messages.isLoading ? <p className="text-center text-sm text-muted-foreground">{common("loading")}</p> : messages.isError ? <div className="text-center"><p className="text-sm text-destructive">{t("messageError")}</p><Button className="mt-2" size="sm" variant="outline" onClick={() => messages.refetch()}>{common("tryAgain")}</Button></div> : !messages.data?.items.length ? <p className="text-center text-sm text-muted-foreground">{common("noData")}</p> : messages.data.items.map((message) => <MessageBubble key={message.id} message={message} />)}
        <div ref={messagesEndRef} />
      </main>
      <form className="flex items-end gap-2 border-t border-border bg-card p-3" onSubmit={(event) => { event.preventDefault(); submit(); }}>
        <textarea ref={composerRef} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleComposerKeyDown} rows={1} className="min-h-10 max-h-32 flex-1 resize-y rounded-md border bg-background px-3 py-2 text-sm" placeholder={t("composer.placeholder")} />
        <Button type="submit" size="icon" disabled={!draft.trim() || send.isPending} aria-label={t("composer.send")}><Send /></Button>
      </form>
    </div>
  );
}

function ConversationContext({ conversation }: { conversation: ConversationDTO | null }) {
  const t = useTranslations("inbox");
  if (!conversation) return null;
  return (
    <aside className="hidden min-h-0 overflow-y-auto border-l border-border bg-card xl:block">
      <div className="border-b border-border p-4"><h2 className="text-sm font-semibold">{t("context.title")}</h2><p className="mt-1 text-xs text-muted-foreground">{t("context.description")}</p></div>
      <div className="space-y-5 p-4">
        <div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-md bg-muted text-muted-foreground"><UserRound className="size-4" /></span><div className="min-w-0"><p className="truncate text-sm font-medium">{conversation.subject || t("context.customer")}</p><p className="truncate text-xs text-muted-foreground">{conversation.customer_id}</p></div></div>
        <dl className="space-y-4 text-sm">
          <div><dt className="text-xs text-muted-foreground">{t("context.channel")}</dt><dd className="mt-1"><ChannelBadge channel={conversation.channel} /></dd></div>
          <div><dt className="text-xs text-muted-foreground">{t("context.mode")}</dt><dd className="mt-1"><StatusBadge status={conversation.ai_mode} /></dd></div>
          <div><dt className="text-xs text-muted-foreground">{t("context.attention")}</dt><dd className="mt-1 font-medium">{conversation.needs_attention ? t("context.required") : t("context.clear")}</dd></div>
          <div><dt className="text-xs text-muted-foreground">{t("context.unread")}</dt><dd className="mt-1 font-medium tabular-nums">{conversation.unread_count}</dd></div>
        </dl>
      </div>
    </aside>
  );
}

export function InboxView() {
  const t = useTranslations("inbox");
  const common = useTranslations("common");
  const params = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(params.get("conversation"));
  const [search, setSearch] = useState("");
  const [channel, setChannel] = useState("all");
  const [mode, setMode] = useState("all");
  const [attention, setAttention] = useState(false);
  const [unread, setUnread] = useState(false);
  const query = useConversations({ page: 1, page_size: 100, sort_by: "last_message_at", order: "desc" });
  const items = useMemo(() => (query.data?.items ?? []).filter((item) => {
    const text = `${item.subject ?? ""} ${item.customer_id}`.toLowerCase();
    return text.includes(search.toLowerCase()) && (channel === "all" || item.channel === channel) && (mode === "all" || item.ai_mode === mode) && (!attention || item.needs_attention) && (!unread || item.unread_count > 0);
  }), [query.data?.items, search, channel, mode, attention, unread]);
  const selected = (query.data?.items ?? []).find((item) => item.id === selectedId) ?? null;

  return (
    <div className="h-[calc(100dvh-7rem)] min-h-[560px] overflow-hidden rounded-lg border border-border bg-card">
      <div className="grid h-full min-h-0 grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)] xl:grid-cols-[320px_minmax(0,1fr)_280px]">
        <aside className={cn("min-h-0 flex-col border-r border-border bg-card", selectedId ? "hidden lg:flex" : "flex")}>
          <div className="border-b border-border p-4"><h1 className="text-lg font-semibold">{t("title")}</h1><p className="text-xs text-muted-foreground">{t("description")}</p></div>
          <div className="space-y-2 border-b border-border p-3">
            <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("search")} />
            <div className="grid grid-cols-2 gap-2"><select value={channel} onChange={(event) => setChannel(event.target.value)} className="h-9 rounded-md border bg-background px-2 text-xs"><option value="all">{t("allChannels")}</option><option value="web">WebChat</option><option value="line">LINE</option><option value="facebook">Facebook</option></select><select value={mode} onChange={(event) => setMode(event.target.value)} className="h-9 rounded-md border bg-background px-2 text-xs"><option value="all">{t("allModes")}</option><option value="AUTO">AUTO</option><option value="COPILOT">COPILOT</option><option value="HUMAN">HUMAN</option></select></div>
            <div className="flex gap-2"><Button size="sm" variant={attention ? "default" : "outline"} onClick={() => setAttention(!attention)}>{t("needsAttention")}</Button><Button size="sm" variant={unread ? "default" : "outline"} onClick={() => setUnread(!unread)}>{t("unread")}</Button></div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {query.isLoading ? <p className="p-6 text-center text-sm text-muted-foreground">{common("loading")}</p> : query.isError ? <div className="p-6 text-center"><p className="text-sm text-destructive">{t("conversationError")}</p><Button className="mt-2" variant="outline" onClick={() => query.refetch()}>{common("tryAgain")}</Button></div> : !items.length ? <p className="p-6 text-center text-sm text-muted-foreground">{t("noMatches")}</p> : items.map((item) => <button key={item.id} onClick={() => setSelectedId(item.id)} className={cn("block w-full border-b border-border p-4 text-left transition-colors hover:bg-muted/45", selectedId === item.id && "bg-brand-soft")}><div className="flex justify-between gap-2"><p className="truncate font-medium">{item.subject || item.customer_id}</p><ChannelBadge channel={item.channel} /></div><div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><StatusBadge status={item.ai_mode} />{item.needs_attention ? <span className="font-medium text-warning">{t("needsAttention")}</span> : null}{item.unread_count ? <span className="rounded-md bg-brand px-1.5 py-0.5 font-semibold text-brand-foreground">{item.unread_count}</span> : null}</div></button>)}
          </div>
        </aside>
        <div className={cn("min-h-0", selectedId ? "block" : "hidden lg:block")}><Chat conversation={selected} onBack={() => setSelectedId(null)} /></div>
        <ConversationContext conversation={selected} />
      </div>
    </div>
  );
}
