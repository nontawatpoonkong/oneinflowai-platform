"use client";

import { FormEvent, useRef, useState } from "react";
import { Bot, Loader2, MessageCircle, Send, X } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/services/api/errors";
import { sendDemoMessage } from "@/services/demo/demo-chat.service";
import type { DemoChatMessage, DemoLanguage } from "@/types/demo-chat";

const languageCommands: Record<DemoLanguage, Set<string>> = {
  th: new Set([
    "ตอบเป็นภาษาไทย",
    "ขอภาษาไทย",
    "ใช้ภาษาไทย",
    "คุยภาษาไทย",
    "ภาษาไทย",
    "please reply in thai",
    "answer in thai",
    "need thai language",
  ]),
  en: new Set([
    "ตอบเป็นภาษาอังกฤษ",
    "ขอภาษาอังกฤษ",
    "use english",
    "reply in english",
    "answer in english",
  ]),
};

function detectLanguagePreference(message: string): DemoLanguage | null {
  const normalized = message
    .trim()
    .toLocaleLowerCase()
    .replace(/[.!?]+$/, "")
    .replace(/\s+/g, " ");
  return (
    (Object.entries(languageCommands).find(([, commands]) =>
      commands.has(normalized),
    )?.[0] as DemoLanguage | undefined) ?? null
  );
}

export function DemoChat() {
  const t = useTranslations("demoChat");
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<DemoChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [preferredLanguage, setPreferredLanguage] = useState<DemoLanguage | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || pending) return;
    const userMessage = { id: crypto.randomUUID(), role: "user" as const, content };
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setError("");
    setPending(true);
    try {
      const requestedLanguage = detectLanguagePreference(content);
      const result = await sendDemoMessage(
        content,
        messages,
        requestedLanguage ?? preferredLanguage,
      );
      if (requestedLanguage) setPreferredLanguage(requestedLanguage);
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", content: result.answer, citations: result.citations }]);
    } catch (requestError) {
      const code = requestError instanceof ApiError ? requestError.code : "";
      setError(code === "DEMO_RATE_LIMIT_EXCEEDED" ? t("rateLimited") : code === "DEMO_RATE_LIMIT_UNAVAILABLE" ? t("unavailable") : t("error"));
    } finally {
      setPending(false);
      window.requestAnimationFrame(() => inputRef.current?.focus());
    }
  }

  return (
    <div className="fixed bottom-5 right-5 z-[100]">
      {open ? <section aria-label={t("title")} className="mb-3 flex h-[min(620px,80dvh)] w-[min(390px,calc(100vw-2rem))] flex-col overflow-hidden rounded-3xl border bg-background shadow-2xl">
        <header className="flex items-center gap-3 bg-slate-950 px-4 py-4 text-white"><Bot className="size-5 text-brand" /><div className="flex-1"><p className="font-semibold">{t("title")}</p><p className="text-xs text-slate-400">{t("subtitle")}</p></div><Button variant="ghost" size="icon" onClick={() => setOpen(false)} aria-label={t("close")}><X className="size-4" /></Button></header>
        <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
          {!messages.length ? <p className="rounded-2xl bg-muted p-3 text-sm">{t("welcome")}</p> : null}
          {messages.map((message) => <div key={message.id} className={message.role === "user" ? "ml-8 rounded-2xl bg-brand p-3 text-sm text-brand-foreground" : "mr-8 rounded-2xl bg-muted p-3 text-sm"}><p className="whitespace-pre-wrap">{message.content}</p>{message.citations?.length ? <p className="mt-2 text-[11px] text-muted-foreground">{t("sources")}: {message.citations.map((item) => item.source).join(", ")}</p> : null}</div>)}
          {pending ? <Loader2 className="size-5 animate-spin text-brand" /> : null}{error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        <form onSubmit={submit} className="flex gap-2 border-t p-3"><textarea ref={inputRef} value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={1000} rows={1} placeholder={t("placeholder")} className="min-h-10 flex-1 resize-none rounded-xl border bg-background px-3 py-2 text-sm" /><Button type="submit" size="icon" disabled={!draft.trim() || pending} aria-label={t("send")}><Send className="size-4" /></Button></form>
      </section> : null}
      <Button size="lg" className="rounded-full shadow-xl" onClick={() => setOpen((value) => !value)} aria-label={t("open")}><MessageCircle className="size-5" /> {t("launcher")}</Button>
    </div>
  );
}
