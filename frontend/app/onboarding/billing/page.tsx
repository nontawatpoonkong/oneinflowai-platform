"use client";

import { AlertTriangle, CheckCircle2, Clock3, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { AuthGuard } from "@/components/dashboard/shell/auth-guard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useBillingOnboarding } from "@/hooks/api/use-billing";
import { useCreateWorkspace, useWorkspaces } from "@/hooks/api/use-workspace";

export default function BillingOnboardingPage() {
  return <AuthGuard requireWorkspace={false}><BillingOnboarding /></AuthGuard>;
}

function BillingOnboarding() {
  const t = useTranslations("billingOnboarding");
  const router = useRouter();
  const workspaces = useWorkspaces();
  const billing = useBillingOnboarding();
  const createWorkspace = useCreateWorkspace();
  const [name, setName] = useState("");
  const subscription = billing.account.data?.subscriptions.find(
    (item)=>item.status!=="CANCELED"&&item.status!=="EXPIRED",
  ) ?? null;
  const eligible = subscription?.status === "ACTIVE" || subscription?.status === "TRIALING";
  const canProvision = eligible && subscription.allocated_workspaces < subscription.workspace_limit;

  useEffect(() => {
    if (workspaces.data?.length) router.replace("/dashboard");
  }, [router, workspaces.data]);

  async function selectPlan(planId: string) {
    try {
      await billing.createSubscription.mutateAsync(planId);
      toast.success(t("subscriptionCreated"));
    } catch {
      toast.error(t("subscriptionError"));
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || !subscription || !canProvision) return;
    try {
      await createWorkspace.mutateAsync({name:name.trim(),subscriptionId:subscription.id});
      toast.success(t("workspaceCreated"));
      router.replace("/dashboard");
    } catch {
      toast.error(t("workspaceError"));
    }
  }

  if (billing.plans.isLoading || billing.account.isLoading || workspaces.isLoading) {
    return <main className="grid min-h-dvh place-items-center"><Loader2 className="size-7 animate-spin text-primary" /></main>;
  }

  if (billing.plans.isError || billing.account.isError) {
    return <State icon={AlertTriangle} title={t("loadError")} action={()=>{void billing.plans.refetch();void billing.account.refetch();}} actionLabel={t("retry")} />;
  }

  return (
    <main className="min-h-dvh bg-muted/30 p-6">
      <section className="mx-auto w-full max-w-4xl rounded-3xl border bg-card p-6 shadow-sm sm:p-8">
        <Link className="text-sm text-muted-foreground hover:text-foreground" href="/onboarding/workspace">← {t("back")}</Link>
        <h1 className="mt-5 text-2xl font-semibold">{t("title")}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t("description")}</p>

        {!subscription ? (
          <div className="mt-8 grid gap-4 md:grid-cols-2">
            {billing.plans.data?.length ? billing.plans.data.map((plan) => (
              <article key={plan.id} className="rounded-2xl border p-5">
                <h2 className="font-semibold">{plan.display_name}</h2>
                <p className="mt-2 text-sm text-muted-foreground">{plan.pricing_note ?? t("pilotPricing")}</p>
                <Button className="mt-5 w-full" disabled={billing.createSubscription.isPending} onClick={()=>selectPlan(plan.id)}>
                  {billing.createSubscription.isPending?<Loader2 className="size-4 animate-spin"/>:null}{t("selectPlan")}
                </Button>
              </article>
            )) : <p className="text-sm text-muted-foreground">{t("noPlans")}</p>}
          </div>
        ) : subscription.status === "PENDING_ACTIVATION" ? (
          <div className="mt-8 rounded-2xl border border-amber-400/40 bg-amber-50 p-6 text-amber-950 dark:bg-amber-950/20 dark:text-amber-100">
            <Clock3 className="size-7" />
            <h2 className="mt-3 text-lg font-semibold">{t("pendingTitle")}</h2>
            <p className="mt-2 text-sm">{t("pendingDescription")}</p>
            <Badge className="mt-4" variant="outline">{subscription.status}</Badge>
            <Button className="mt-5 block" variant="outline" onClick={()=>billing.account.refetch()}>{t("refresh")}</Button>
          </div>
        ) : canProvision ? (
          <form className="mt-8 rounded-2xl border p-6" onSubmit={submit}>
            <CheckCircle2 className="size-7 text-emerald-600" />
            <h2 className="mt-3 text-lg font-semibold">{t("readyTitle")}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{t("readyDescription",{plan:subscription.plan.display_name})}</p>
            <Label className="mt-5 block" htmlFor="workspace-name">{t("workspaceName")}</Label>
            <Input id="workspace-name" className="mt-2" maxLength={255} value={name} onChange={(event)=>setName(event.target.value)} />
            <Button className="mt-4" disabled={!name.trim()||createWorkspace.isPending}>
              {createWorkspace.isPending?<Loader2 className="size-4 animate-spin"/>:null}{t("createWorkspace")}
            </Button>
          </form>
        ) : (
          <div className="mt-8 rounded-2xl border p-6">
            <AlertTriangle className="size-7 text-destructive" />
            <h2 className="mt-3 text-lg font-semibold">{t("unavailableTitle")}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{t("unavailableDescription",{status:subscription.status})}</p>
          </div>
        )}
      </section>
    </main>
  );
}

function State({icon:Icon,title,action,actionLabel}:{icon:typeof AlertTriangle;title:string;action:()=>void;actionLabel:string}) {
  return <main className="grid min-h-dvh place-items-center p-6"><section className="text-center"><Icon className="mx-auto size-8 text-destructive"/><p className="mt-3">{title}</p><Button className="mt-4" variant="outline" onClick={action}>{actionLabel}</Button></section></main>;
}
