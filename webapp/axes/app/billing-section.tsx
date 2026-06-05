"use client";

import { useCallback, useEffect, useState } from "react";

import { isValidPaddlePriceId } from "@/lib/paddle/config";
import { usePaddle } from "@/lib/paddle/use-paddle";

type BillingSectionProps = {
  clientToken: string;
  basePriceId: string;
  customerEmail: string;
  customerName: string | null;
  tenantId: string;
};

type BillingStatus = {
  billing_setup: boolean;
  paddle_customer_id: string | null;
  paddle_subscription_id: string | null;
  subscription_status: string | null;
};

const WEBHOOK_POLL_ATTEMPTS = 8;
const WEBHOOK_POLL_INTERVAL_MS = 1000;

export function BillingSection({
  clientToken,
  basePriceId,
  customerEmail,
  customerName,
  tenantId,
}: BillingSectionProps) {
  const [billingStatus, setBillingStatus] = useState<BillingStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [portalError, setPortalError] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [webhookWaitLoading, setWebhookWaitLoading] = useState(false);

  const refreshBillingStatus = useCallback(async (): Promise<BillingStatus | null> => {
    setStatusLoading(true);
    setStatusError(null);

    try {
      const response = await fetch("/api/billing/status");
      const payload = (await response.json()) as BillingStatus & { detail?: string };

      if (!response.ok) {
        throw new Error(payload.detail ?? "Could not load billing status.");
      }

      setBillingStatus(payload);
      return payload;
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setStatusError(message);
      return null;
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshBillingStatus();
  }, [refreshBillingStatus]);

  const waitForWebhookBillingSetup = useCallback(async (): Promise<void> => {
    setWebhookWaitLoading(true);
    setCheckoutError(null);

    try {
      for (let attempt = 0; attempt < WEBHOOK_POLL_ATTEMPTS; attempt += 1) {
        if (attempt > 0) {
          await new Promise((resolve) => {
            setTimeout(resolve, WEBHOOK_POLL_INTERVAL_MS);
          });
        }

        const status = await refreshBillingStatus();
        if (status?.billing_setup) {
          return;
        }
      }

      setCheckoutError(
        "Checkout completed, but billing is not active yet. Wait a few seconds and refresh the page.",
      );
    } finally {
      setWebhookWaitLoading(false);
    }
  }, [refreshBillingStatus]);

  const paddle = usePaddle(clientToken, {
    onCheckoutCompleted: () => {
      void waitForWebhookBillingSetup();
    },
    onCheckoutError: ({ message }) => {
      setCheckoutError(message);
    },
  });

  function openCheckout(): void {
    if (!isValidPaddlePriceId(basePriceId)) {
      setCheckoutError(
        "Invalid Paddle price ID. Set NEXT_PUBLIC_PADDLE_BASE_PRICE_ID in .env.local to a real sandbox price ID (starts with pri_).",
      );
      return;
    }

    if (!paddle) {
      setCheckoutError("Paddle checkout is still loading. Try again in a moment.");
      return;
    }

    setCheckoutError(null);
    paddle.Checkout.open({
      items: [{ priceId: basePriceId, quantity: 1 }],
      customer: {
        email: customerEmail,
      },
      customData: {
        tenant_id: tenantId,
      },
    });
  }

  async function openCustomerPortal(): Promise<void> {
    setPortalError(null);
    setPortalLoading(true);

    try {
      const response = await fetch("/api/billing/portal", { method: "POST" });
      const payload = (await response.json()) as { url?: string; detail?: string };

      if (!response.ok) {
        throw new Error(payload.detail ?? "Could not open Paddle customer portal.");
      }

      if (!payload.url) {
        throw new Error("Paddle did not return a customer portal URL.");
      }

      window.open(payload.url, "_blank", "noopener,noreferrer");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setPortalError(message);
    } finally {
      setPortalLoading(false);
    }
  }

  const billingReady = billingStatus?.billing_setup === true;
  const setupButtonLabel = webhookWaitLoading
    ? "Activating billing…"
    : paddle
      ? "Set up billing"
      : "Loading…";

  return (
    <section className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <h2 className="text-sm font-medium text-zinc-950 dark:text-zinc-50">Billing</h2>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        Add a payment method once through Paddle. Your card is stored securely by Paddle — we only
        keep billing reference IDs for this tenant. Usage is charged monthly based on token
        consumption.
      </p>

      {statusLoading ? (
        <p className="mt-3 text-sm text-zinc-500">Checking billing status…</p>
      ) : statusError ? (
        <p className="mt-3 text-sm text-red-600">{statusError}</p>
      ) : billingReady ? (
        <p className="mt-3 text-sm text-green-700 dark:text-green-400">
          Billing is active
          {billingStatus?.subscription_status ? ` (${billingStatus.subscription_status})` : ""}.
          Monthly usage charges are billed automatically.
        </p>
      ) : (
        <p className="mt-3 text-sm text-amber-700 dark:text-amber-400">
          No payment method on file yet. Set up billing to enable monthly usage charges.
        </p>
      )}

      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        {!billingReady ? (
          <button
            type="button"
            onClick={openCheckout}
            disabled={!paddle || webhookWaitLoading}
            className="inline-flex h-10 items-center justify-center rounded-full bg-zinc-950 px-4 text-sm font-medium text-white transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-zinc-50 dark:text-zinc-950 dark:hover:bg-zinc-200"
          >
            {setupButtonLabel}
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => {
            void openCustomerPortal();
          }}
          disabled={portalLoading || !billingReady}
          className="inline-flex h-10 items-center justify-center rounded-full border border-zinc-200 px-4 text-sm font-medium text-zinc-950 transition-colors hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:text-zinc-50 dark:hover:bg-zinc-900"
        >
          {portalLoading ? "Opening portal…" : "Manage billing"}
        </button>
      </div>

      {checkoutError ? <p className="mt-3 text-sm text-red-600">{checkoutError}</p> : null}
      {portalError ? <p className="mt-3 text-sm text-red-600">{portalError}</p> : null}

      {!billingReady && customerName ? (
        <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-500">Billing contact: {customerName}.</p>
      ) : null}
    </section>
  );
}
