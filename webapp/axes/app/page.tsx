import { redirect } from "next/navigation";

import { auth0 } from "@/lib/auth0";
import { BillingSection } from "@/app/billing-section";
import { IntegrationSection } from "@/app/integration-section";
import { getPaddlePublicConfig } from "@/lib/paddle/config";
import {
  ApiUnauthorizedError,
  buildGithubInstallUrl,
  buildSalesforceConnectUrl,
  buildSalesforceInstallUrl,
  buildSlackInstallUrl,
  fetchAppIntegrationsForSession,
  findGithubIntegration,
  findSalesforceIntegration,
  findSlackIntegration,
  githubInstallationId,
  resolveTenantForSession,
  salesforceOrgId,
  slackTeamId,
  type AppIntegrationRecord,
  type TenantRecord,
} from "@/lib/tenants";

function redirectToLoginIfUnauthorized(error: unknown): void {
  if (error instanceof ApiUnauthorizedError) {
    redirect("/auth/login");
  }
}

async function loadTenantForSession(
  session: NonNullable<Awaited<ReturnType<typeof auth0.getSession>>>,
): Promise<{ tenant: TenantRecord | null; error: string | null }> {
  try {
    const tenant = await resolveTenantForSession(session);
    return { tenant, error: null };
  } catch (error: unknown) {
    redirectToLoginIfUnauthorized(error);
    const message = error instanceof Error ? error.message : String(error);
    console.error("Tenant resolution failed:", message);
    return { tenant: null, error: message };
  }
}

async function loadAppIntegrationsForSession(
  session: NonNullable<Awaited<ReturnType<typeof auth0.getSession>>>,
): Promise<{ integrations: AppIntegrationRecord[]; error: string | null }> {
  try {
    const integrations = await fetchAppIntegrationsForSession(session);
    return { integrations, error: null };
  } catch (error: unknown) {
    redirectToLoginIfUnauthorized(error);
    const message = error instanceof Error ? error.message : String(error);
    console.error("App integrations lookup failed:", message);
    return { integrations: [], error: message };
  }
}

export default async function Home() {
  const session = await auth0.getSession();

  if (!session?.tokenSet?.idToken) {
    redirect("/auth/login");
  }

  const { tenant, error: tenantResolveError } = await loadTenantForSession(session);
  const { integrations, error: integrationsError } = tenant
    ? await loadAppIntegrationsForSession(session)
    : { integrations: [], error: null };
  const tenantId = tenant?.id ?? null;
  const tenantName = tenant?.name ?? null;

  const slackTeam = slackTeamId(findSlackIntegration(integrations));
  const githubInstallation = githubInstallationId(findGithubIntegration(integrations));
  const salesforceOrg = salesforceOrgId(findSalesforceIntegration(integrations));

  const slackInstallUrl = tenantId && !slackTeam ? buildSlackInstallUrl(tenantId) : null;
  const githubInstallUrl = tenantId && !githubInstallation ? buildGithubInstallUrl(tenantId) : null;
  const salesforceInstallUrl = tenantId && !salesforceOrg ? buildSalesforceInstallUrl(tenantId) : null;
  const salesforceConnectUrl = tenantId && !salesforceOrg ? buildSalesforceConnectUrl(tenantId) : null;
  const paddleConfig = getPaddlePublicConfig();
  const customerEmail = session.user.email ?? tenant?.email ?? null;

  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-zinc-50 px-6 py-24 font-sans dark:bg-black">
      <main className="flex w-full max-w-2xl flex-col gap-6 rounded-2xl border border-zinc-200 bg-white p-8 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-zinc-950 dark:text-zinc-50">Axes</h1>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              Logged in as {session.user.email ?? session.user.name ?? session.user.sub}
            </p>
          </div>
          <a
            href="/auth/logout"
            className="inline-flex h-10 items-center justify-center rounded-full border border-zinc-200 px-4 text-sm font-medium text-zinc-950 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-50 dark:hover:bg-zinc-900"
          >
            Log out
          </a>
        </div>

        <section className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-950 dark:text-zinc-50">Tenant</h2>
          {tenantId ? (
            <dl className="mt-3 space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
              <div>
                <dt className="font-medium text-zinc-950 dark:text-zinc-50">Name</dt>
                <dd>{tenantName ?? "—"}</dd>
              </div>
              <div>
                <dt className="font-medium text-zinc-950 dark:text-zinc-50">ID</dt>
                <dd className="font-mono text-xs break-all">{tenantId}</dd>
              </div>
            </dl>
          ) : (
            <p className="mt-3 text-sm text-red-600">{tenantResolveError ?? "Could not resolve tenant."}</p>
          )}
        </section>

        {tenantId && paddleConfig && customerEmail ? (
          <BillingSection
            clientToken={paddleConfig.clientToken}
            basePriceId={paddleConfig.basePriceId}
            customerEmail={customerEmail}
            customerName={session.user.name ?? tenantName}
            tenantId={tenantId}
          />
        ) : null}

        {tenantId ? (
          <>
            <IntegrationSection
              title="Slack"
              error={integrationsError}
              installedFields={slackTeam ? [{ label: "Team ID", value: slackTeam }] : null}
              notConnectedMessage="Install the Axes Slack app for this tenant."
              installUrl={slackInstallUrl}
              installLabel="Install Slack app"
            />
            <IntegrationSection
              title="GitHub"
              error={integrationsError}
              installedFields={
                githubInstallation ? [{ label: "Installation ID", value: githubInstallation }] : null
              }
              notConnectedMessage="Install the Axes GitHub App for this tenant."
              installUrl={githubInstallUrl}
              installLabel="Install GitHub App"
            />
            <IntegrationSection
              title="Salesforce"
              error={integrationsError}
              installedFields={salesforceOrg ? [{ label: "Org ID", value: salesforceOrg }] : null}
              notConnectedMessage="Install AxesRev in Salesforce (opens a new tab), then return here and connect your integration user."
              installUrl={salesforceInstallUrl}
              installLabel="Install AxesRev"
              secondaryUrl={salesforceConnectUrl}
              secondaryLabel="Connect org"
            />
          </>
        ) : null}
      </main>
    </div>
  );
}
