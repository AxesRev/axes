import { NextResponse } from "next/server";

import { auth0 } from "@/lib/auth0";
import { isPaddleBillingConfigured } from "@/lib/paddle/config";
import { ApiResponseError, fetchBillingPortalUrlForAccessToken } from "@/lib/tenants";

export async function POST(): Promise<NextResponse> {
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
    const url = await fetchBillingPortalUrlForAccessToken(session.tokenSet.idToken);
    return NextResponse.json({ url });
  } catch (error: unknown) {
    if (error instanceof ApiResponseError) {
      console.error("Billing portal failed:", error.message);
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    const message = error instanceof Error ? error.message : String(error);
    console.error("Billing portal failed:", message);
    return NextResponse.json({ detail: "Could not create a Paddle customer portal session." }, { status: 502 });
  }
}
