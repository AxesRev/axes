export const PADDLE_SANDBOX_ENVIRONMENT = "sandbox" as const;

export type PaddlePublicConfig = {
  clientToken: string;
  basePriceId: string;
};

export function getPaddlePublicConfig(): PaddlePublicConfig | null {
  const clientToken = process.env.NEXT_PUBLIC_PADDLE_CLIENT_TOKEN?.trim();
  const basePriceId =
    process.env.NEXT_PUBLIC_PADDLE_BASE_PRICE_ID?.trim() ??
    process.env.NEXT_PUBLIC_PADDLE_PRICE_ID?.trim();

  if (!clientToken || !basePriceId) {
    return null;
  }

  return {
    clientToken,
    basePriceId,
  };
}

export function isPaddleBillingConfigured(): boolean {
  return getPaddlePublicConfig() !== null && Boolean(process.env.PADDLE_API_KEY?.trim());
}

export function isValidPaddlePriceId(priceId: string): boolean {
  return /^pri_[a-z0-9]+$/i.test(priceId);
}
