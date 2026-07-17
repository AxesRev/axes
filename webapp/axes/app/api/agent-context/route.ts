import { NextResponse } from "next/server";

import { auth0 } from "@/lib/auth0";
import {
  ApiResponseError,
  ApiUnauthorizedError,
  fetchAgentContextForAccessToken,
  updateAgentContextForAccessToken,
} from "@/lib/tenants";

export async function GET(): Promise<NextResponse> {
  const session = await auth0.getSession();
  if (!session?.tokenSet?.idToken) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }

  try {
    const context = await fetchAgentContextForAccessToken(session.tokenSet.idToken);
    return NextResponse.json(context);
  } catch (error: unknown) {
    if (error instanceof ApiUnauthorizedError) {
      return NextResponse.json({ detail: error.message }, { status: 401 });
    }
    const message = error instanceof Error ? error.message : String(error);
    console.error("Agent context lookup failed:", message);
    return NextResponse.json({ detail: "Could not load agent context." }, { status: 502 });
  }
}

export async function PUT(request: Request): Promise<NextResponse> {
  const session = await auth0.getSession();
  if (!session?.tokenSet?.idToken) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }

  let body: { content?: unknown };
  try {
    body = (await request.json()) as { content?: unknown };
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body." }, { status: 400 });
  }

  if (typeof body.content !== "string") {
    return NextResponse.json({ detail: "content must be a string." }, { status: 400 });
  }

  try {
    const context = await updateAgentContextForAccessToken(session.tokenSet.idToken, body.content);
    return NextResponse.json(context);
  } catch (error: unknown) {
    if (error instanceof ApiUnauthorizedError) {
      return NextResponse.json({ detail: error.message }, { status: 401 });
    }
    if (error instanceof ApiResponseError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }
    const message = error instanceof Error ? error.message : String(error);
    console.error("Agent context update failed:", message);
    return NextResponse.json({ detail: "Could not save agent context." }, { status: 502 });
  }
}
