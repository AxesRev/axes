import type { SessionData } from "@auth0/nextjs-auth0/types";

export type TenantRecord = {
  id: string;
  name: string;
  email: string | null;
};

export async function resolveTenantForAccessToken(accessToken: string): Promise<TenantRecord> {
  const apiBaseUrl = (process.env.AEGRA_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

  const response = await fetch(`${apiBaseUrl}/tenants/me`, {
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
