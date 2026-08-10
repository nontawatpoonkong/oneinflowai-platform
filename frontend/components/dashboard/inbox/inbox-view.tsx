"use client";

import {
  Facebook,
  Globe,
  Instagram,
  MessageCircle,
  MessagesSquare,
  Send,
  ShoppingBag,
  Sparkles,
  Tag,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { toast, Toaster } from "sonner";

import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useConversations } from "@/hooks/api/use-conversations";
import { useConversationOperations } from "@/hooks/api/use-conversation-operations";
import { useMessages } from "@/hooks/api/use-messages";
import { useSendMessage } from "@/hooks/api/use-send-message";
import { useUpdateConversation } from "@/hooks/api/use-update-conversation";
import { useWorkspaceMembers } from "@/hooks/api/use-workspace";
import { cn } from "@/lib/utils";
import type { ConversationAiModeDTO, ConversationDTO } from "@/types/api";
import type { MessageDTO } from "@/types/message";
import { formatCurrencyTHB, initialsFrom } from "@/utils/format";

/* ------------------------------- view data ------------------------------- */

type Channel = "line" | "facebook" | "web" | "instagram";
type LeadStatus = "new" | "hot" | "warm" | "cold";

interface Order {
  id: string;
  item: string;
  amount: number;
  date: string;
}

interface Conversation {
  id: string;
  name: string;
  channel: Channel;
  lastMessage: string;
  time: string;
  unread: number;
  email: string;
  phone: string;
  tags: string[];
  leadStatus: LeadStatus;
  orders: Order[];
  aiMode: ConversationAiModeDTO;
  workspaceId: string;
  assignedUserId: string | null;
  needsAttention: boolean;
  handoffReason: string | null;
}

function toConversation(dto: ConversationDTO): Conversation {
  const activityAt = dto.last_message_at ?? dto.updated_at;

  return {
    id: dto.id,
    name: dto.subject || dto.customer_id,
    channel:
      dto.channel === "line" ||
      dto.channel === "facebook" ||
      dto.channel === "instagram"
        ? dto.channel
        : "web",
    lastMessage: dto.subject || "—",
    time: new Date(activityAt).toLocaleString(),
    unread: dto.unread_count,
    email: "—",
    phone: "—",
    tags: [],
    leadStatus: "new",
    orders: [],
    aiMode: dto.ai_mode,
    workspaceId: dto.workspace_id,
    assignedUserId: dto.assigned_user_id,
    needsAttention: dto.needs_attention,
    handoffReason: dto.handoff_reason,
  };
}

const AI_MODE_LABEL: Record<ConversationAiModeDTO, string> = {
  AUTO: "AI อัตโนมัติ",
  COPILOT: "ผู้ช่วย AI",
  HUMAN: "เจ้าหน้าที่ตอบ",
};

const CHANNEL_ICON: Record<Channel, LucideIcon> = {
  line: MessageCircle,
  facebook: Facebook,
  web: Globe,
  instagram: Instagram,
};

const LEAD_TONE: Record<LeadStatus, string> = {
  new: "bg-brand",
  hot: "bg-positive",
  warm: "bg-warning",
  cold: "bg-muted-foreground",
};

/* ------------------------------- components ------------------------------ */

function ChannelBadge({ channel }: { channel: Channel }) {
  const t = useTranslations("inbox.channels");
  const Icon = CHANNEL_ICON[channel];
  return (
    <Badge variant="muted" className="px-2 py-0.5 text-[11px]">
      <Icon className="size-3" />
      {t(channel)}
    </Badge>
  );
}

function MessageBubble({ message }: { message: MessageDTO }) {
  const createdAt = new Intl.DateTimeFormat("th-TH", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(message.created_at));

  if (message.sender_type === "system") {
    return (
      <div className="flex justify-center">
        <div className="max-w-[75%] text-center text-xs text-muted-foreground">
          <p className="font-medium">System</p>
          <p>{message.content}</p>
          <p className="mt-1 text-[10px]">{createdAt}</p>
        </div>
      </div>
    );
  }

  const isCustomer = message.sender_type === "customer";
  const isAi = message.sender_type === "ai";

  return (
    <div className={cn("flex", isCustomer ? "justify-start" : "justify-end")}>
      <div
        className={cn(
          "max-w-[75%] rounded-2xl px-4 py-2.5 text-sm shadow-soft",
          isCustomer && "rounded-bl-sm bg-card",
          message.sender_type === "agent" &&
            "rounded-br-sm bg-brand text-brand-foreground",
          isAi && "rounded-br-sm bg-brand/10 text-foreground",
        )}
      >
        {isAi ? (
          <p className="mb-1 text-[10px] font-medium text-brand">AI</p>
        ) : null}
        <p>{message.content}</p>
        <p
          className={cn(
            "mt-1 text-[10px]",
            message.sender_type === "agent"
              ? "text-brand-foreground/70"
              : "text-muted-foreground",
          )}
        >
          {createdAt}
        </p>
      </div>
    </div>
  );
}

function ConversationList({
  conversations,
  isLoading,
  isError,
  onRetry,
  selectedId,
  onSelect,
}: {
  conversations: Conversation[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const t = useTranslations("inbox");
  const tCommon = useTranslations("common");
  const tErrors = useTranslations("errors");
  return (
    <div className="flex h-full flex-col border-b border-border lg:border-b-0 lg:border-r">
      <div className="border-b border-border p-3">
        <Input placeholder={t("search")} aria-label={t("search")} />
      </div>
      <ul className="flex-1 overflow-y-auto">
        {isLoading ? (
          <li className="grid h-full place-items-center p-6 text-sm text-muted-foreground">
            {tCommon("loading")}
          </li>
        ) : isError ? (
          <li className="grid h-full place-items-center p-6 text-center">
            <div>
              <p className="text-sm text-muted-foreground">
                {tErrors("serverDesc")}
              </p>
              <Button
                className="mt-3"
                size="sm"
                variant="outline"
                onClick={onRetry}
              >
                {tCommon("tryAgain")}
              </Button>
            </div>
          </li>
        ) : conversations.length === 0 ? (
          <li className="grid h-full place-items-center p-6 text-center text-sm text-muted-foreground">
            {tCommon("noData")}
          </li>
        ) : (
          conversations.map((conversation) => {
            const active = selectedId === conversation.id;
            return (
              <li key={conversation.id}>
                <button
                  type="button"
                  onClick={() => onSelect(conversation.id)}
                  aria-current={active ? "true" : undefined}
                  className={cn(
                    "flex w-full items-start gap-3 border-l-2 px-4 py-3 text-left transition-colors",
                    active
                      ? "border-brand bg-brand/5"
                      : "border-transparent hover:bg-accent",
                  )}
                >
                  <span className="grid size-10 shrink-0 place-items-center rounded-full bg-brand/10 text-xs font-semibold text-brand">
                    {initialsFrom(conversation.name, conversation.name)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-sm font-medium">
                        {conversation.name}
                      </p>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {conversation.time}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-sm text-muted-foreground">
                      {conversation.lastMessage}
                    </p>
                    <div className="mt-1.5 flex items-center justify-between gap-2">
                      <ChannelBadge channel={conversation.channel} />
                      {conversation.needsAttention ? (
                        <span className="rounded-full bg-warning/15 px-2 py-0.5 text-[10px] font-medium text-warning">
                          {t("needsAttention")}
                        </span>
                      ) : null}
                      {conversation.unread > 0 ? (
                        <span className="grid min-w-5 place-items-center rounded-full bg-brand px-1.5 text-xs font-semibold text-brand-foreground">
                          {conversation.unread}
                        </span>
                      ) : null}
                    </div>
                  </div>
                </button>
              </li>
            );
          })
        )}
      </ul>
    </div>
  );
}

function ChatWindow({ conversation }: { conversation: Conversation | null }) {
  const t = useTranslations("inbox");
  const tCommon = useTranslations("common");
  const tErrors = useTranslations("errors");
  const [draft, setDraft] = useState("");
  const { data, isLoading, isError, refetch } = useMessages(
    conversation?.id ?? null,
    { page: 1, page_size: 100 },
  );
  const sendMessage = useSendMessage(conversation?.id ?? null);
  const updateConversation = useUpdateConversation(conversation?.id ?? null);
  const operations = useConversationOperations(conversation?.id ?? null);
  const members = useWorkspaceMembers(conversation?.workspaceId);
  const markRead = operations.markRead;

  useEffect(() => {
    if (conversation?.unread) markRead.mutate();
  }, [conversation?.id, conversation?.unread, markRead]);

  function handleSubmit() {
    const content = draft.trim();
    if (!content || sendMessage.isPending || !conversation) return;

    sendMessage.mutate(content, {
      onSuccess: () => setDraft(""),
      onError: (error) => {
        toast.error(
          error instanceof Error ? error.message : tErrors("serverDesc"),
        );
      },
    });
  }

  if (!conversation) {
    return (
      <div className="grid h-full place-items-center p-6">
        <EmptyState
          icon={MessagesSquare}
          title={t("empty.title")}
          description={t("empty.desc")}
          className="border-0 bg-transparent"
        />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-border p-4">
        <span className="grid size-9 shrink-0 place-items-center rounded-full bg-brand/10 text-xs font-semibold text-brand">
          {initialsFrom(conversation.name, conversation.name)}
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{conversation.name}</p>
          <ChannelBadge channel={conversation.channel} />
        </div>
        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
        {conversation.aiMode === "HUMAN" ? (
          <Button size="sm" variant="outline" onClick={() => operations.returnToAi.mutate()}>
            {t("returnToAi")}
          </Button>
        ) : (
          <Button size="sm" variant="outline" onClick={() => operations.handoff.mutate()}>
            {t("handoff")}
          </Button>
        )}
        <Button size="sm" variant="outline" onClick={() => operations.assign.mutate(undefined)}>
          {t("assignToMe")}
        </Button>
        <select
          value={conversation.assignedUserId ?? ""}
          onChange={(event) => event.target.value && operations.assign.mutate(event.target.value)}
          aria-label={t("assignMember")}
          className="h-9 rounded-md border border-input bg-background px-2 text-xs"
        >
          <option value="">{t("assignMember")}</option>
          {members.data?.map((member) => (
            <option key={member.user_id} value={member.user_id}>
              {member.full_name || member.email}
            </option>
          ))}
        </select>
        <select
          value={conversation.aiMode}
          onChange={(event) => {
            const mode = event.target.value as ConversationAiModeDTO;
            if (mode === "HUMAN") {
              operations.handoff.mutate();
              return;
            }
            if (mode === "AUTO") {
              operations.returnToAi.mutate();
              return;
            }
            updateConversation.mutate(
              mode,
              {
                onError: (error) => {
                  toast.error(
                    error instanceof Error
                      ? error.message
                      : tErrors("serverDesc"),
                  );
                },
              },
            );
          }}
          disabled={updateConversation.isPending}
          aria-label="โหมดการตอบสนทนา"
          className="h-9 rounded-md border border-input bg-background px-2 text-xs font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        >
          {(Object.keys(AI_MODE_LABEL) as ConversationAiModeDTO[]).map(
            (mode) => (
              <option key={mode} value={mode}>
                {AI_MODE_LABEL[mode]}
              </option>
            ),
          )}
        </select>
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto bg-muted/10 p-4">
        {isLoading ? (
          <div className="grid h-full place-items-center text-sm text-muted-foreground">
            {tCommon("loading")}
          </div>
        ) : isError ? (
          <div className="grid h-full place-items-center text-center">
            <div>
              <p className="text-sm text-muted-foreground">
                {tErrors("serverDesc")}
              </p>
              <Button
                className="mt-3"
                size="sm"
                variant="outline"
                onClick={() => void refetch()}
              >
                {tCommon("tryAgain")}
              </Button>
            </div>
          </div>
        ) : data?.items.length === 0 ? (
          <div className="grid h-full place-items-center text-sm text-muted-foreground">
            {tCommon("noData")}
          </div>
        ) : (
          data?.items.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))
        )}
      </div>

      <form
        className="flex items-center gap-2 border-t border-border p-3"
        onSubmit={(event) => {
          event.preventDefault();
          handleSubmit();
        }}
      >
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              handleSubmit();
            }
          }}
          rows={1}
          disabled={sendMessage.isPending}
          placeholder={t("composer.placeholder")}
          aria-label={t("composer.placeholder")}
          className="flex min-h-10 max-h-32 w-full resize-none overflow-y-auto rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        />
        <Button
          type="submit"
          size="icon"
          disabled={!draft.trim() || sendMessage.isPending}
          aria-label="send"
        >
          <Send className="size-4" />
        </Button>
      </form>
      <p className="px-3 pb-2 text-xs text-muted-foreground">{t("composer.hint")}</p>
    </div>
  );
}

function CustomerSidebar({ conversation }: { conversation: Conversation | null }) {
  const t = useTranslations("inbox.customer");
  const tLead = useTranslations("inbox.leadStatuses");

  if (!conversation) {
    return (
      <div className="hidden h-full place-items-center border-t border-border p-6 text-center lg:grid lg:border-l lg:border-t-0">
        <p className="text-sm text-muted-foreground">{t("selectPrompt")}</p>
      </div>
    );
  }

  return (
    <div className="hidden h-full flex-col gap-5 overflow-y-auto border-t border-border p-5 lg:flex lg:border-l lg:border-t-0">
      <div className="flex flex-col items-center gap-2 text-center">
        <span className="grid size-14 place-items-center rounded-full bg-brand/10 text-base font-semibold text-brand">
          {initialsFrom(conversation.name, conversation.name)}
        </span>
        <div>
          <p className="font-semibold">{conversation.name}</p>
          <p className="text-xs text-muted-foreground">{conversation.email}</p>
          <p className="text-xs text-muted-foreground">{conversation.phone}</p>
        </div>
      </div>

      <div>
        <p className="mb-2 inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Tag className="size-3.5" /> {t("tags")}
        </p>
        <div className="flex flex-wrap gap-1.5">
          {conversation.tags.map((tag) => (
            <Badge key={tag} variant="outline">
              {tag}
            </Badge>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between rounded-xl border border-border bg-muted/20 px-3 py-2">
        <span className="text-xs font-medium text-muted-foreground">{t("leadStatus")}</span>
        <span className="inline-flex items-center gap-1.5 text-sm font-medium">
          <span className={cn("size-2 rounded-full", LEAD_TONE[conversation.leadStatus])} />
          {tLead(conversation.leadStatus)}
        </span>
      </div>

      <Card className="bg-brand/5 p-4">
        <p className="mb-1.5 inline-flex items-center gap-1.5 text-xs font-medium text-brand">
          <Sparkles className="size-3.5" /> {t("aiSummary")}
        </p>
        <p className="text-sm text-muted-foreground">{t("aiSummaryPlaceholder")}</p>
      </Card>

      <div>
        <p className="mb-2 inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <ShoppingBag className="size-3.5" /> {t("recentOrders")}
        </p>
        {conversation.orders.length === 0 ? (
          <p className="rounded-xl border border-dashed border-border bg-muted/20 px-3 py-4 text-center text-xs text-muted-foreground">
            {t("noOrders")}
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {conversation.orders.map((order) => (
              <li
                key={order.id}
                className="flex items-center justify-between rounded-xl border border-border px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{order.item}</p>
                  <p className="text-xs text-muted-foreground">
                    {order.id} · {order.date}
                  </p>
                </div>
                <span className="shrink-0 text-sm font-semibold tabular-nums">
                  {formatCurrencyTHB(order.amount)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/* --------------------------------- view ---------------------------------- */

export function InboxView() {
  const searchParams = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(
    searchParams.get("conversation"),
  );
  const { data, isLoading, isError, refetch } = useConversations({
    page: 1,
    page_size: 100,
    sort_by: "last_message_at",
    order: "desc",
  });
  const conversations = useMemo(
    () => (data?.items ?? []).map(toConversation),
    [data?.items],
  );
  const selected = conversations.find((c) => c.id === selectedId) ?? null;

  return (
    <div className="h-[calc(100dvh-7rem)] min-h-[560px] overflow-hidden rounded-2xl border border-border bg-card">
      <Toaster richColors position="top-right" />
      <div className="grid h-full grid-cols-1 lg:grid-cols-[320px_1fr_340px]">
        <ConversationList
          conversations={conversations}
          isLoading={isLoading}
          isError={isError}
          onRetry={() => void refetch()}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
        <ChatWindow conversation={selected} />
        <CustomerSidebar conversation={selected} />
      </div>
    </div>
  );
}
