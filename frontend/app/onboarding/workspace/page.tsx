"use client";

import { ArrowRight, Building2, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { AuthGuard } from "@/components/dashboard/shell/auth-guard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useMyAccessRequests, useWorkspaces } from "@/hooks/api/use-workspace";
import { workspaceService } from "@/services/workspace/workspace.service";

export default function WorkspaceOnboardingPage() {
  return <AuthGuard requireWorkspace={false}><WorkspaceOnboarding /></AuthGuard>;
}

function WorkspaceOnboarding() {
  const t = useTranslations("workspaceOnboarding");
  const router = useRouter();
  const workspaces = useWorkspaces();
  const requests = useMyAccessRequests();
  const [code, setCode] = useState("");
  const [resolvedName, setResolvedName] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const pendingRequest = requests.data?.find((item) => item.status === "PENDING");

  useEffect(() => {
    if (workspaces.data?.length) router.replace("/dashboard");
  }, [router, workspaces.data]);

  async function resolveCode() {
    if (!code.trim()) return;
    setIsSubmitting(true);
    try {
      const result = await workspaceService.resolveJoinCode(code);
      setResolvedName(result.name);
    } catch {
      setResolvedName(null);
      toast.error(t("invalidCode"));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function requestAccess() {
    setIsSubmitting(true);
    try {
      await workspaceService.requestAccess({ code });
      await requests.refetch();
      setResolvedName(null);
      toast.success(t("requestSent"));
    } catch {
      toast.error(t("requestFailed"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-dvh place-items-center bg-muted/30 p-6">
      <section className="w-full max-w-2xl rounded-3xl border bg-card p-6 shadow-sm sm:p-8">
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t("description")}</p>
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border p-5">
            <Building2 className="size-6 text-primary" />
            <h2 className="mt-3 font-semibold">{t("createTitle")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t("createDescription")}</p>
            <Button asChild className="mt-5 w-full">
              <Link href="/onboarding/billing">{t("choosePlan")}<ArrowRight className="size-4" /></Link>
            </Button>
          </div>
          <div className="rounded-2xl border border-cyan-400/40 p-5">
            <Users className="size-6 text-primary" />
            <h2 className="mt-3 font-semibold">{t("joinTitle")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t("joinDescription")}</p>
            {pendingRequest ? (
              <div className="mt-5 rounded-xl border border-pink-400/30 bg-pink-400/5 p-4 text-sm">
                <p className="font-medium">{t("pendingTitle")}</p>
                <p className="mt-1 text-muted-foreground">
                  {pendingRequest.workspace_name ?? t("workspace")}
                </p>
              </div>
            ) : resolvedName ? (
              <div className="mt-5 space-y-3 rounded-xl border bg-muted/30 p-4">
                <p className="text-sm text-muted-foreground">{t("workspaceFound")}</p>
                <p className="font-semibold">{resolvedName}</p>
                <Button className="w-full" onClick={requestAccess} disabled={isSubmitting}>
                  {t("confirmRequest")}
                </Button>
                <Button className="w-full" variant="ghost" onClick={() => setResolvedName(null)}>
                  {t("useAnotherCode")}
                </Button>
              </div>
            ) : (
              <div className="mt-5 space-y-3">
                <Input
                  value={code}
                  onChange={(event) => setCode(event.target.value.toUpperCase())}
                  placeholder={t("codePlaceholder")}
                  autoComplete="off"
                />
                <Button className="w-full" variant="outline" onClick={resolveCode} disabled={isSubmitting || !code.trim()}>
                  {t("findWorkspace")}
                </Button>
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
