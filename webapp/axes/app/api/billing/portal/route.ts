import { NextResponse } from "next/server";

import { auth0 } from "@/lib/auth0";
import { createCustomerPortalUrl } from "@/lib/paddle/server";
import { isPaddleBillingConfigured } from "@/lib/paddle/config";
import { fetchBillingStatusForAccessToken } from "@/lib/tenants";

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
    const billingStatus = await fetchBillingStatusForAccessToken(session.tokenSet.idToken);
    const customerId = billingStatus.paddle_customer_id;
    if (!customerId) {
      return NextResponse.json(
        {
          detail:
            "Billing is not set up for this tenant yet. Add a payment method through Paddle checkout first.",
        },
        { status: 404 },
      );
    }

    const url = await createCustomerPortalUrl(customerId, billingStatus.paddle_subscription_id);
    return NextResponse.json({ url });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error("Paddle customer portal session failed:", message);
    return NextResponse.json(
      { detail: "Could not create a Paddle customer portal session." },
      { status: 502 },
    );
  }
}
