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
import { useState } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { formatCurrencyTHB, initialsFrom } from "@/utils/format";

/* ------------------------------- mock data ------------------------------- */

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
}

const CONVERSATIONS: Conversation[] = [
  {
    id: "c1",
    name: "คุณสมชาย ใจดี",
    channel: "line",
    lastMessage: "สนใจห้อง Deluxe สุดสัปดาห์นี้ครับ",
    time: "2 นาที",
    unread: 3,
    email: "somchai@example.com",
    phone: "081-234-5678",
    tags: ["VIP", "สนใจห้องพัก"],
    leadStatus: "hot",
    orders: [
      { id: "#1042", item: "ห้อง Deluxe 2 คืน", amount: 4800, date: "10 ก.ค." },
      { id: "#0988", item: "อาหารเช้า x2", amount: 560, date: "2 มิ.ย." },
    ],
  },
  {
    id: "c2",
    name: "Sarah Johnson",
    channel: "facebook",
    lastMessage: "Is breakfast included in the price?",
    time: "15 นาที",
    unread: 0,
    email: "sarah.j@example.com",
    phone: "090-111-2222",
    tags: ["ลูกค้าใหม่"],
    leadStatus: "warm",
    orders: [],
  },
  {
    id: "c3",
    name: "คุณมานี รักดี",
    channel: "web",
    lastMessage: "ขอบคุณสำหรับข้อมูลค่ะ",
    time: "1 ชม.",
    unread: 1,
    email: "manee@example.com",
    phone: "089-777-6543",
    tags: ["ลูกค้าประจำ"],
    leadStatus: "new",
    orders: [],
  },
  {
    id: "c4",
    name: "Nattapong K.",
    channel: "instagram",
    lastMessage: "ราคาสุทธิรวมทุกอย่างเท่าไหร่",
    time: "3 ชม.",
    unread: 0,
    email: "nattapong@example.com",
    phone: "086-543-2100",
    tags: ["สอบถามราคา"],
    leadStatus: "cold",
    orders: [],
  },
  {
    id: "c5",
    name: "คุณอรุณี แสงทอง",
    channel: "line",
    lastMessage: "ขอจองวันที่ 12 นะคะ",
    time: "เมื่อวาน",
    unread: 0,
    email: "arunee@example.com",
    phone: "082-909-0909",
    tags: ["VIP"],
    leadStatus: "hot",
    orders: [{ id: "#1030", item: "ห้อง Superior 1 คืน", amount: 1900, date: "8 ก.ค." }],
  },
];

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

function ConversationList({
  selectedId,
  onSelect,
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const t = useTranslations("inbox");
  return (
    <div className="flex h-full flex-col border-b border-border lg:border-b-0 lg:border-r">
      <div className="border-b border-border p-3">
        <Input placeholder={t("search")} aria-label={t("search")} />
      </div>
      <ul className="flex-1 overflow-y-auto">
        {CONVERSATIONS.map((conversation) => {
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
                    <p className="truncate text-sm font-medium">{conversation.name}</p>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {conversation.time}
                    </span>
                  </div>
                  <p className="mt-0.5 truncate text-sm text-muted-foreground">
                    {conversation.lastMessage}
                  </p>
                  <div className="mt-1.5 flex items-center justify-between gap-2">
                    <ChannelBadge channel={conversation.channel} />
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
        })}
      </ul>
    </div>
  );
}

function ChatWindow({ conversation }: { conversation: Conversation | null }) {
  const t = useTranslations("inbox");

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
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto bg-muted/10 p-4">
        <div className="flex justify-start">
          <div className="max-w-[75%] rounded-2xl rounded-bl-sm bg-card px-4 py-2.5 text-sm shadow-soft">
            {conversation.lastMessage}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 border-t border-border p-3">
        <Input placeholder={t("composer.placeholder")} disabled aria-label={t("composer.placeholder")} />
        <Button size="icon" disabled aria-label="send">
          <Send className="size-4" />
        </Button>
      </div>
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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = CONVERSATIONS.find((c) => c.id === selectedId) ?? null;

  return (
    <div className="h-[calc(100dvh-7rem)] min-h-[560px] overflow-hidden rounded-2xl border border-border bg-card">
      <div className="grid h-full grid-cols-1 lg:grid-cols-[320px_1fr_340px]">
        <ConversationList selectedId={selectedId} onSelect={setSelectedId} />
        <ChatWindow conversation={selected} />
        <CustomerSidebar conversation={selected} />
      </div>
    </div>
  );
}
