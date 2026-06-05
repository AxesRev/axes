import { NextResponse } from "next/server";

import { auth0 } from "@/lib/auth0";
import { isPaddleBillingConfigured } from "@/lib/paddle/config";
import { ApiResponseError, linkBillingForAccessToken } from "@/lib/tenants";

type LinkRequestBody = {
  paddle_customer_id?: string;
  paddle_transaction_id?: string;
};

export async function POST(request: Request): Promise<NextResponse> {
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

  let body: LinkRequestBody;
  try {
    body = (await request.json()) as LinkRequestBody;
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body." }, { status: 400 });
  }

  const paddleCustomerId = body.paddle_customer_id?.trim();
  const paddleTransactionId = body.paddle_transaction_id?.trim();
  if (!paddleCustomerId || !paddleTransactionId) {
    return NextResponse.json(
      { detail: "paddle_customer_id and paddle_transaction_id are required." },
      { status: 400 },
    );
  }

  try {
    const status = await linkBillingForAccessToken(session.tokenSet.idToken, {
      paddle_customer_id: paddleCustomerId,
      paddle_transaction_id: paddleTransactionId,
    });
    return NextResponse.json(status);
  } catch (error: unknown) {
    if (error instanceof ApiResponseError) {
      console.error("Billing link failed:", error.message);
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    const message = error instanceof Error ? error.message : String(error);
    console.error("Billing link failed:", message);
    return NextResponse.json({ detail: "Could not link Paddle billing to this tenant." }, { status: 502 });
  }
}
