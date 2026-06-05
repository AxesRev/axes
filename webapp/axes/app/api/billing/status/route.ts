import { NextResponse } from "next/server";

import { auth0 } from "@/lib/auth0";
import { isPaddleBillingConfigured } from "@/lib/paddle/config";
import { fetchBillingStatusForAccessToken } from "@/lib/tenants";

export async function GET(): Promise<NextResponse> {
  if (!isPaddleBillingConfigured()) {
    return NextResponse.json(
      { detail: "Paddle sandbox billing is not configured on this app." },
      { status: 503 },
    );
  }

  const session = await auth0.getSession();
  if (!session?.tokenSet?.idToken) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }

  try {
    const status = await fetchBillingStatusForAccessToken(session.tokenSet.idToken);
    return NextResponse.json(status);
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error("Billing status lookup failed:", message);
    return NextResponse.json({ detail: "Could not load billing status." }, { status: 502 });
  }
}
