"use client";

import { FormEvent, useEffect, useState } from "react";
import { Loader2, MessageCircle, RotateCw, Send } from "lucide-react";

import {
  useCreateWebChatSession,
  useSendWebChatMessage,
  useWebChatMessages,
} from "@/hooks/api/use-webchat";
import type { StoredWebChatSession } from "@/types/webchat";

const storageKey = (workspaceKey: string) => `webchat:${workspaceKey}`;

export function WebChatView({ workspaceKey }: { workspaceKey: string }) {
  const [session, setSession] = useState<StoredWebChatSession | null>(null);
  const [ready, setReady] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [content, setContent] = useState("");
  const createSession = useCreateWebChatSession();
  const messages = useWebChatMessages(session);
  const sendMessage = useSendWebChatMessage(session);

  useEffect(() => {
    const stored = sessionStorage.getItem(storageKey(workspaceKey));
    if (stored) {
      try {
        setSession(JSON.parse(stored) as StoredWebChatSession);
      } catch {
        sessionStorage.removeItem(storageKey(workspaceKey));
      }
    }
    setReady(true);
  }, [workspaceKey]);

  async function start(event: FormEvent) {
    event.preventDefault();
    const result = await createSession.mutateAsync({
      workspace_key: workspaceKey,
      name,
      email: email || undefined,
      language: navigator.language,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      landing_url: window.location.href,
      referrer: document.referrer || undefined,
    });
    const next = {
      conversationId: result.conversation_id,
      token: result.session_token,
    };
    sessionStorage.setItem(storageKey(workspaceKey), JSON.stringify(next));
    setSession(next);
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const trimmed = content.trim();
    if (!trimmed) return;
    await sendMessage.mutateAsync(trimmed);
    setContent("");
  }

  if (!ready) return null;

  return (
    <main className="flex min-h-dvh items-center justify-center bg-slate-100 p-0 sm:p-4">
      <section className="flex h-dvh w-full max-w-lg flex-col overflow-hidden bg-white shadow-xl sm:h-[760px] sm:rounded-2xl">
        <header className="flex items-center gap-3 bg-slate-900 px-5 py-4 text-white">
          <MessageCircle className="h-6 w-6" />
          <div><h1 className="font-semibold">WebChat</h1><p className="text-xs text-slate-300">{workspaceKey}</p></div>
        </header>

        {!session ? (
          <form onSubmit={start} className="m-auto w-full space-y-4 p-6">
            <div><h2 className="text-xl font-semibold">เริ่มการสนทนา</h2><p className="mt-1 text-sm text-slate-500">กรอกชื่อเพื่อพูดคุยกับเจ้าหน้าที่</p></div>
            <input required maxLength={150} value={name} onChange={(e) => setName(e.target.value)} placeholder="ชื่อ" className="w-full rounded-lg border px-3 py-2.5 outline-none focus:ring-2 focus:ring-slate-500" />
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="อีเมล (ไม่บังคับ)" className="w-full rounded-lg border px-3 py-2.5 outline-none focus:ring-2 focus:ring-slate-500" />
            {createSession.isError && <p className="text-sm text-red-600">ไม่สามารถเริ่มการสนทนาได้ กรุณาลองใหม่</p>}
            <button disabled={createSession.isPending} className="flex w-full items-center justify-center rounded-lg bg-slate-900 px-4 py-2.5 text-white disabled:opacity-50">
              {createSession.isPending ? <Loader2 className="h-5 w-5 animate-spin" /> : "เริ่มแชต"}
            </button>
          </form>
        ) : (
          <>
            <div className="flex-1 space-y-3 overflow-y-auto p-4">
              {messages.isPending && <div className="flex h-full items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>}
              {messages.isError && <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-slate-500"><p>โหลดข้อความไม่สำเร็จ</p><button onClick={() => messages.refetch()} className="flex items-center gap-2 rounded-lg border px-3 py-2"><RotateCw className="h-4 w-4" />ลองใหม่</button></div>}
              {messages.data?.items.length === 0 && <div className="flex h-full items-center justify-center text-sm text-slate-400">ยังไม่มีข้อความ เริ่มพิมพ์ด้านล่างได้เลย</div>}
              {messages.data?.items.map((message) => {
                const customer = message.sender_type === "customer";
                return <div key={message.id} className={`flex ${customer ? "justify-end" : "justify-start"}`}><div className={`max-w-[82%] rounded-2xl px-4 py-2 ${customer ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-900"}`}><p className="whitespace-pre-wrap break-words text-sm">{message.content}</p><time className={`mt-1 block text-[10px] ${customer ? "text-slate-300" : "text-slate-400"}`}>{new Intl.DateTimeFormat("th-TH", { hour: "2-digit", minute: "2-digit" }).format(new Date(message.created_at))}</time></div></div>;
              })}
            </div>
            <form onSubmit={send} className="border-t p-3">
              {sendMessage.isError && <p className="mb-2 text-xs text-red-600">ส่งข้อความไม่สำเร็จ กรุณาลองใหม่</p>}
              <div className="flex items-end gap-2"><textarea rows={1} maxLength={4000} value={content} onChange={(e) => setContent(e.target.value)} placeholder="พิมพ์ข้อความ..." disabled={sendMessage.isPending} className="max-h-32 flex-1 resize-none overflow-y-auto rounded-xl border px-3 py-2.5 outline-none focus:ring-2 focus:ring-slate-500 disabled:opacity-50" /><button aria-label="ส่งข้อความ" disabled={!content.trim() || sendMessage.isPending} className="rounded-xl bg-slate-900 p-3 text-white disabled:opacity-40">{sendMessage.isPending ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}</button></div>
            </form>
          </>
        )}
      </section>
    </main>
  );
}
