import { WebChatView } from "@/components/webchat/webchat-view";

export default async function WebChatPage({
  params,
}: {
  params: Promise<{ workspaceKey: string }>;
}) {
  const { workspaceKey } = await params;
  return <WebChatView workspaceKey={workspaceKey} />;
}
