"use client";

import { CheckoutEventNames, type Paddle, type PaddleEventData, initializePaddle } from "@paddle/paddle-js";
import { useEffect, useRef, useState } from "react";

import { PADDLE_SANDBOX_ENVIRONMENT } from "@/lib/paddle/config";

export type CheckoutCompletedPayload = {
  customerId: string;
  transactionId: string;
};

export type CheckoutErrorPayload = {
  message: string;
};

type UsePaddleOptions = {
  onCheckoutCompleted?: (payload: CheckoutCompletedPayload) => void;
  onCheckoutError?: (payload: CheckoutErrorPayload) => void;
};

function checkoutErrorMessage(event: PaddleEventData): string {
  if ("detail" in event && typeof event.detail === "string" && event.detail) {
    return event.detail;
  }
  if ("code" in event && typeof event.code === "string" && event.code) {
    return `Paddle checkout error (${event.code}).`;
  }
  return "Paddle checkout failed. Check your sandbox price ID and default payment link in the Paddle dashboard.";
}

export function usePaddle(clientToken: string, options?: UsePaddleOptions): Paddle | undefined {
  const [paddle, setPaddle] = useState<Paddle>();
  const onCheckoutCompletedRef = useRef(options?.onCheckoutCompleted);
  const onCheckoutErrorRef = useRef(options?.onCheckoutError);
  onCheckoutCompletedRef.current = options?.onCheckoutCompleted;
  onCheckoutErrorRef.current = options?.onCheckoutError;

  useEffect(() => {
    let cancelled = false;

    initializePaddle({
      environment: PADDLE_SANDBOX_ENVIRONMENT,
      token: clientToken,
      checkout: {
        settings: {
          displayMode: "overlay",
          variant: "one-page",
        },
      },
      eventCallback: (event: PaddleEventData) => {
        if (
          event.name === CheckoutEventNames.CHECKOUT_ERROR ||
          event.name === CheckoutEventNames.CHECKOUT_FAILED ||
          event.name === CheckoutEventNames.CHECKOUT_PAYMENT_ERROR ||
          event.name === CheckoutEventNames.CHECKOUT_PAYMENT_FAILED
        ) {
          onCheckoutErrorRef.current?.({ message: checkoutErrorMessage(event) });
          return;
        }

        if (event.name !== CheckoutEventNames.CHECKOUT_COMPLETED || !event.data) {
          return;
        }

        const customerId = event.data.customer.id;
        const transactionId = event.data.transaction_id;
        const onCheckoutCompleted = onCheckoutCompletedRef.current;
        if (!customerId || !transactionId || !onCheckoutCompleted) {
          return;
        }

        onCheckoutCompleted({ customerId, transactionId });
      },
    }).then((paddleInstance: Paddle | undefined) => {
      if (!cancelled && paddleInstance) {
        setPaddle(paddleInstance);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [clientToken]);

  return paddle;
}
