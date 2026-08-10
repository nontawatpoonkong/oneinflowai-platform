"use client";

import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import {
  ArrowUp,
  Bot,
  Loader2,
  MessageCircle,
  Minus,
  RotateCw,
  Sparkles,
  X,
} from "lucide-react";

import {
  useCreateWebChatSession,
  useDecideWebChatAction,
  useSendWebChatMessage,
  useWebChatMessages,
} from "@/hooks/api/use-webchat";
import type { StoredWebChatSession, WebChatAssistantResult } from "@/types/webchat";

const sessionKey = (workspaceKey: string) => `webchat:${workspaceKey}`;
const openKey = (workspaceKey: string) => `webchat:open:${workspaceKey}`;
const focusableSelector =
  'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface WebChatWidgetProps {
  workspaceKey: string;
  workspaceName?: string;
  defaultOpen?: boolean;
}

export function WebChatWidget({
  workspaceKey,
  workspaceName = "OneInFlow",
  defaultOpen = false,
}: WebChatWidgetProps) {
  const [session, setSession] = useState<StoredWebChatSession | null>(null);
  const [ready, setReady] = useState(false);
  const [open, setOpen] = useState(defaultOpen);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [content, setContent] = useState("");
  const [latestAssistant, setLatestAssistant] =
    useState<WebChatAssistantResult | null>(null);
  const pendingMessageId = useRef<string | null>(null);
  const panelRef = useRef<HTMLElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const createSession = useCreateWebChatSession();
  const messages = useWebChatMessages(session);
  const sendMessage = useSendWebChatMessage(session);
  const decideAction = useDecideWebChatAction(session);

  useEffect(() => {
    const storedSession = sessionStorage.getItem(sessionKey(workspaceKey));
    if (storedSession) {
      try {
        const parsed = JSON.parse(storedSession) as StoredWebChatSession;
        if (parsed.conversationId && parsed.token) setSession(parsed);
        else sessionStorage.removeItem(sessionKey(workspaceKey));
      } catch {
        sessionStorage.removeItem(sessionKey(workspaceKey));
      }
    }

    const storedOpen = localStorage.getItem(openKey(workspaceKey));
    if (storedOpen !== null) setOpen(storedOpen === "true");
    setReady(true);
  }, [workspaceKey]);

  useEffect(() => {
    if (!ready) return;
    localStorage.setItem(openKey(workspaceKey), String(open));
  }, [open, ready, workspaceKey]);

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => {
      (session ? composerRef.current : nameRef.current)?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open, session]);

  useEffect(() => {
    if (open && messages.data?.items.length) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages.data?.items.length, open]);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        launcherRef.current?.focus();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(focusableSelector),
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  useEffect(() => {
    const textarea = composerRef.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 112)}px`;
  }, [content]);

  async function start(event: FormEvent) {
    event.preventDefault();
    const result = await createSession.mutateAsync({
      workspace_key: workspaceKey,
      name: name.trim(),
      email: email.trim() || undefined,
      language: navigator.language,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      landing_url: window.location.href,
      referrer: document.referrer || undefined,
    });
    const next = {
      conversationId: result.conversation_id,
      token: result.session_token,
    };
    sessionStorage.setItem(sessionKey(workspaceKey), JSON.stringify(next));
    setSession(next);
  }

  async function submitMessage() {
    const trimmed = content.trim();
    if (!trimmed || sendMessage.isPending) return;
    pendingMessageId.current ??= crypto.randomUUID();
    const result = await sendMessage.mutateAsync({
      content: trimmed,
      client_message_id: pendingMessageId.current,
    });
    pendingMessageId.current = null;
    setLatestAssistant(result.assistant);
    setContent("");
  }

  async function submitAction(decision: "confirm" | "cancel") {
    const collection = latestAssistant?.action_collection;
    if (!collection) return;
    const result = await decideAction.mutateAsync({
      collectionId: collection.session_id,
      decision,
      payload: {
        client_message_id: crypto.randomUUID(),
        confirmation_token:
          decision === "confirm"
            ? collection.confirmation_token ?? undefined
            : undefined,
      },
    });
    setLatestAssistant(result);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitMessage();
    }
  }

  function close() {
    setOpen(false);
    window.requestAnimationFrame(() => launcherRef.current?.focus());
  }

  if (!ready) return null;

  return (
    <div className="fixed inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-[100] flex flex-col items-end sm:inset-x-auto sm:bottom-6 sm:right-6">
      <section
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-hidden={!open}
        className={`mb-3 flex h-[80dvh] max-h-[600px] w-full max-w-[420px] origin-bottom-right flex-col overflow-hidden rounded-[28px] border border-black/[0.07] bg-white text-slate-950 shadow-[0_32px_100px_-24px_rgba(2,8,23,0.55),0_8px_30px_-12px_rgba(2,8,23,0.22)] transition-[opacity,transform,visibility] duration-300 ease-out sm:h-[600px] sm:w-[380px] ${
          open
            ? "visible translate-y-0 scale-100 opacity-100"
            : "invisible translate-y-3 scale-[0.96] opacity-0 pointer-events-none"
        }`}
      >
        <header className="relative overflow-hidden bg-[#07101d] px-5 pb-5 pt-4 text-white">
          <div className="absolute -right-12 -top-14 size-40 rounded-full bg-brand/20 blur-3xl" />
          <div className="relative flex items-start gap-3">
            <div className="relative grid size-11 shrink-0 place-items-center rounded-[15px] border border-white/10 bg-white/[0.08] shadow-inner">
              <Sparkles className="size-5 text-brand" />
              <span className="absolute -bottom-0.5 -right-0.5 size-3.5 rounded-full border-[3px] border-[#07101d] bg-emerald-400" />
            </div>
            <div className="min-w-0 flex-1 pt-0.5">
              <h2 id={titleId} className="truncate text-[15px] font-semibold tracking-[-0.01em]">
                {workspaceName}
              </h2>
              <p id={descriptionId} className="mt-1 text-[12px] leading-4 text-slate-400">
                Typically replies within a few minutes
              </p>
            </div>
            <div className="flex gap-0.5">
              <button type="button" onClick={close} aria-label="ย่อหน้าต่างแชต" className="grid size-8 place-items-center rounded-full text-slate-400 transition hover:bg-white/10 hover:text-white">
                <Minus className="size-4" />
              </button>
              <button type="button" onClick={close} aria-label="ปิดหน้าต่างแชต" className="grid size-8 place-items-center rounded-full text-slate-400 transition hover:bg-white/10 hover:text-white">
                <X className="size-4" />
              </button>
            </div>
          </div>
        </header>

        {!session ? (
          <form onSubmit={start} className="flex flex-1 flex-col justify-center px-6 py-8 sm:px-7">
            <div className="mb-7">
              <span className="mb-5 grid size-10 place-items-center rounded-full bg-brand/10 text-brand">
                <MessageCircle className="size-5" />
              </span>
              <h3 className="text-[26px] font-semibold tracking-[-0.035em]">สวัสดี 👋</h3>
              <p className="mt-2 text-sm leading-6 text-slate-500">เริ่มพูดคุยกับทีมของเรา</p>
            </div>
            <div className="space-y-4">
              <label className="block text-xs font-medium text-slate-600">
                ชื่อ <span className="text-red-500">*</span>
                <input ref={nameRef} required maxLength={150} autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} placeholder="ชื่อของคุณ" className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm shadow-sm outline-none transition placeholder:text-slate-400 focus:border-brand focus:ring-4 focus:ring-brand/10" />
              </label>
              <label className="block text-xs font-medium text-slate-600">
                อีเมล <span className="font-normal text-slate-400">(ไม่บังคับ)</span>
                <input type="email" maxLength={254} autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm shadow-sm outline-none transition placeholder:text-slate-400 focus:border-brand focus:ring-4 focus:ring-brand/10" />
              </label>
            </div>
            {createSession.isError && <p role="alert" className="mt-3 text-xs text-red-600">ไม่สามารถเริ่มการสนทนาได้ กรุณาลองใหม่</p>}
            <button type="submit" disabled={createSession.isPending || !name.trim()} className="mt-6 flex w-full items-center justify-center rounded-xl bg-[#07101d] px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-950/10 transition hover:-translate-y-0.5 hover:bg-slate-800 disabled:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50">
              {createSession.isPending ? <Loader2 className="size-5 animate-spin" /> : "เริ่มการสนทนา"}
            </button>
          </form>
        ) : (
          <>
            <div aria-live="polite" className="flex-1 space-y-3 overflow-y-auto bg-[#f7f8fa] px-4 py-5">
              <p className="pb-1 text-center text-[10px] font-medium uppercase tracking-[0.16em] text-slate-400">วันนี้</p>
              {messages.isPending && <div className="flex justify-center py-8"><Loader2 className="size-5 animate-spin text-slate-400" /></div>}
              {messages.isError && (
                <div className="flex flex-col items-center gap-3 py-8 text-xs text-slate-500">
                  <p>โหลดข้อความไม่สำเร็จ</p>
                  <button type="button" onClick={() => messages.refetch()} className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm"><RotateCw className="size-3.5" />ลองใหม่</button>
                </div>
              )}
              {messages.data?.items.length === 0 && (
                <div className="flex items-start gap-2.5">
                  <span className="mt-1 grid size-7 shrink-0 place-items-center rounded-full bg-[#07101d] text-brand"><Bot className="size-3.5" /></span>
                  <div className="max-w-[78%] rounded-[18px] rounded-tl-md bg-white px-3.5 py-2.5 text-sm leading-5 shadow-[0_1px_2px_rgba(15,23,42,0.08)]">สวัสดีค่ะ มีอะไรให้เราช่วยวันนี้ไหมคะ?</div>
                </div>
              )}
              {messages.data?.items.map((message) => {
                const customer = message.sender_type === "customer";
                return (
                  <div key={message.id} className={`flex items-end gap-2.5 ${customer ? "justify-end" : "justify-start"}`}>
                    {!customer && <span className="mb-1 grid size-7 shrink-0 place-items-center rounded-full bg-[#07101d] text-brand"><Bot className="size-3.5" /></span>}
                    <div className={`max-w-[78%] rounded-[18px] px-3.5 py-2.5 text-sm leading-5 shadow-[0_1px_2px_rgba(15,23,42,0.08)] ${customer ? "rounded-br-md bg-[#07101d] text-white" : "rounded-tl-md bg-white text-slate-800"}`}>
                      <p className="whitespace-pre-wrap break-words">{message.content}</p>
                      {!customer && Array.isArray(message.metadata.citations) && (
                        <ul className="mt-2 space-y-1 border-t border-slate-100 pt-2 text-[10px] text-slate-500">
                          {(message.metadata.citations as Array<{ label: string; document_name: string }>).map((citation) => (
                            <li key={`${citation.label}:${citation.document_name}`}>
                              [{citation.label}] {citation.document_name}
                            </li>
                          ))}
                        </ul>
                      )}
                      <time className={`mt-1 block text-[9px] ${customer ? "text-slate-400" : "text-slate-400"}`}>{new Intl.DateTimeFormat("th-TH", { hour: "2-digit", minute: "2-digit" }).format(new Date(message.created_at))}</time>
                    </div>
                  </div>
                );
              })}
              {latestAssistant?.type === "ACTION_CONFIRMATION" && latestAssistant.action_collection && (
                <div className="ml-9 rounded-2xl border border-brand/20 bg-white p-4 text-sm shadow-sm">
                  <p className="font-semibold text-slate-900">Confirm request</p>
                  <dl className="mt-2 space-y-1 text-xs text-slate-600">
                    {latestAssistant.action_collection.summary?.fields?.map((field) => (
                      <div key={field.key} className="flex justify-between gap-4">
                        <dt>{field.label}</dt>
                        <dd className="text-right font-medium text-slate-800">{String(field.value)}</dd>
                      </div>
                    ))}
                  </dl>
                  <div className="mt-3 flex gap-2">
                    <button type="button" disabled={decideAction.isPending} onClick={() => void submitAction("confirm")} className="rounded-lg bg-brand px-3 py-2 text-xs font-semibold text-brand-foreground disabled:opacity-50">Confirm</button>
                    <button type="button" disabled={decideAction.isPending} onClick={() => void submitAction("cancel")} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-50">Cancel</button>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <form onSubmit={(event) => { event.preventDefault(); void submitMessage(); }} className="border-t border-slate-100 bg-white px-3 pb-3 pt-2">
              {sendMessage.isError && <p role="alert" className="mb-1.5 px-2 text-[11px] text-red-600">ส่งข้อความไม่สำเร็จ กรุณาลองใหม่</p>}
              <div className="flex items-end gap-2 rounded-[18px] bg-slate-100 p-1.5 ring-1 ring-transparent transition focus-within:bg-white focus-within:ring-brand/30">
                <textarea ref={composerRef} rows={1} maxLength={4000} value={content} onChange={(event) => setContent(event.target.value)} onKeyDown={handleComposerKeyDown} placeholder="เขียนข้อความ..." aria-label="ข้อความ" disabled={sendMessage.isPending} className="min-h-10 max-h-28 flex-1 resize-none overflow-y-auto bg-transparent px-2 py-2.5 text-sm leading-5 outline-none placeholder:text-slate-400 disabled:opacity-50" />
                <button type="submit" aria-label="ส่งข้อความ" disabled={!content.trim() || sendMessage.isPending} className="grid size-10 shrink-0 place-items-center rounded-[14px] bg-brand text-brand-foreground shadow-sm transition hover:scale-[1.04] disabled:scale-100 disabled:cursor-not-allowed disabled:opacity-35">
                  {sendMessage.isPending ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4 stroke-[2.5]" />}
                </button>
              </div>
              <p className="mt-2 text-center text-[9px] font-medium tracking-wide text-slate-400">POWERED BY ONEINFLOW</p>
            </form>
          </>
        )}
      </section>

      <button ref={launcherRef} type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-haspopup="dialog" aria-label={open ? "ปิดหน้าต่างแชต" : "เปิดหน้าต่างแชต"} className="group relative grid size-14 place-items-center rounded-full bg-[#07101d] text-white shadow-[0_16px_38px_-10px_rgba(2,8,23,0.55)] transition duration-200 hover:-translate-y-1 hover:shadow-[0_20px_45px_-10px_rgba(2,8,23,0.6)] active:translate-y-0 active:scale-95 sm:size-16">
        {!open && <span className="absolute inset-0 -z-10 animate-ping rounded-full bg-brand/20 [animation-duration:2.8s]" />}
        <span className="absolute right-1.5 top-1.5 size-2.5 rounded-full border-2 border-[#07101d] bg-emerald-400 sm:right-2 sm:top-2" />
        {open ? <X className="size-5 transition-transform group-hover:rotate-6" /> : <MessageCircle className="size-6 fill-white/10 transition-transform group-hover:scale-105" />}
      </button>
    </div>
  );
}
