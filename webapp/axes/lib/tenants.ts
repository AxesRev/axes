import type { SessionData } from "@auth0/nextjs-auth0/types";

export type TenantRecord = {
  id: string;
  name: string;
  email: string | null;
};

export type AppIntegrationRecord = {
  id: string;
  app_name: string;
  config: Record<string, unknown>;
};

const SLACK_APP_NAME = "slack";

function apiBaseUrl(): string {
  return (process.env.AEGRA_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}

function publicApiBaseUrl(): string {
  return (process.env.AEGRA_PUBLIC_URL ?? apiBaseUrl()).replace(/\/$/, "");
}

export function buildSlackInstallUrl(tenantId: string): string {
  return `${publicApiBaseUrl()}/slack/oauth/install?tenant_id=${encodeURIComponent(tenantId)}`;
}

export async function resolveTenantForAccessToken(accessToken: string): Promise<TenantRecord> {
  const response = await fetch(`${apiBaseUrl()}/tenants/me`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Tenant resolution failed (${response.status}): ${detail}`);
  }

  return (await response.json()) as TenantRecord;
}

export async function resolveTenantForSession(session: SessionData): Promise<TenantRecord> {
  const idToken = session.tokenSet.idToken;
  if (!idToken) {
    throw new Error("Auth0 ID token is missing from the session.");
  }
  return resolveTenantForAccessToken(idToken);
}

export async function fetchAppIntegrationsForAccessToken(
  accessToken: string,
): Promise<AppIntegrationRecord[]> {
  const response = await fetch(`${apiBaseUrl()}/tenants/me/integrations`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`App integrations lookup failed (${response.status}): ${detail}`);
  }

  return (await response.json()) as AppIntegrationRecord[];
}

export async function fetchAppIntegrationsForSession(
  session: SessionData,
): Promise<AppIntegrationRecord[]> {
  const idToken = session.tokenSet.idToken;
  if (!idToken) {
    throw new Error("Auth0 ID token is missing from the session.");
  }
  return fetchAppIntegrationsForAccessToken(idToken);
}

export function findSlackIntegration(
  integrations: AppIntegrationRecord[],
): AppIntegrationRecord | null {
  return integrations.find((integration) => integration.app_name === SLACK_APP_NAME) ?? null;
}

export function slackTeamId(integration: AppIntegrationRecord | null): string | null {
  if (!integration) {
    return null;
  }
  const teamId = integration.config.team_id;
  return typeof teamId === "string" && teamId ? teamId : null;
}
