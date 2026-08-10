import { WebChatWidget } from "@/components/webchat/webchat-widget";

export function WebChatView({ workspaceKey }: { workspaceKey: string }) {
  return (
    <main className="relative min-h-dvh overflow-hidden bg-[#050816] text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_15%,hsl(var(--brand)/0.15),transparent_34%),radial-gradient(circle_at_80%_75%,rgba(59,130,246,0.12),transparent_32%)]" />
      <div className="relative mx-auto flex min-h-dvh max-w-5xl flex-col justify-center px-6 py-20">
        <p className="mb-4 text-xs font-semibold uppercase tracking-[0.22em] text-brand">
          OneInFlow WebChat
        </p>
        <h1 className="max-w-2xl text-4xl font-semibold tracking-[-0.04em] sm:text-6xl">
          พร้อมช่วยคุณในทุกบทสนทนา
        </h1>
        <p className="mt-5 max-w-lg text-base leading-7 text-slate-400">
          เริ่มพูดคุยกับทีมของเราได้จากมุมขวาล่าง
        </p>
      </div>
      <WebChatWidget workspaceKey={workspaceKey} defaultOpen />
    </main>
  );
}
