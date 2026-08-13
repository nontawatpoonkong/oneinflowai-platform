"use client";

import { Building2, Loader2, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { AuthGuard } from "@/components/dashboard/shell/auth-guard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateWorkspace, useWorkspaces } from "@/hooks/api/use-workspace";

export default function WorkspaceOnboardingPage() {
  return <AuthGuard requireWorkspace={false}><WorkspaceOnboarding /></AuthGuard>;
}

function WorkspaceOnboarding() {
  const t = useTranslations("workspaceOnboarding");
  const router = useRouter();
  const workspaces = useWorkspaces();
  const create = useCreateWorkspace();
  const [name, setName] = useState("");

  useEffect(() => {
    if (workspaces.data?.length) router.replace("/dashboard");
  }, [router, workspaces.data]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      await create.mutateAsync(name.trim());
      toast.success(t("created"));
      router.replace("/dashboard");
    } catch {
      toast.error(t("error"));
    }
  }

  return (
    <main className="grid min-h-dvh place-items-center bg-muted/30 p-6">
      <section className="w-full max-w-2xl rounded-3xl border bg-card p-6 shadow-sm sm:p-8">
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t("description")}</p>
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          <form className="rounded-2xl border p-5" onSubmit={submit}>
            <Building2 className="size-6 text-primary" />
            <h2 className="mt-3 font-semibold">{t("createTitle")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t("createDescription")}</p>
            <Label className="mt-5 block" htmlFor="workspace-name">{t("name")}</Label>
            <Input id="workspace-name" className="mt-2" value={name} maxLength={255} onChange={(event) => setName(event.target.value)} />
            <Button className="mt-4 w-full" disabled={!name.trim() || create.isPending}>
              {create.isPending ? <Loader2 className="size-4 animate-spin" /> : null}{t("create")}
            </Button>
          </form>
          <div className="rounded-2xl border border-dashed p-5">
            <Users className="size-6 text-primary" />
            <h2 className="mt-3 font-semibold">{t("joinTitle")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t("joinDescription")}</p>
            <Button className="mt-5 w-full" variant="outline" disabled>{t("joinPending")}</Button>
          </div>
        </div>
      </section>
    </main>
  );
}
