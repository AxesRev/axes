import { Environment, Paddle } from "@paddle/paddle-node-sdk";

export function getPaddleServerClient(): Paddle | null {
  const apiKey = process.env.PADDLE_API_KEY?.trim();
  if (!apiKey) {
    return null;
  }

  return new Paddle(apiKey, {
    environment: Environment.sandbox,
  });
}

export async function findPaddleCustomerIdByEmail(email: string): Promise<string | null> {
  const paddle = getPaddleServerClient();
  if (!paddle) {
    return null;
  }

  const customerCollection = paddle.customers.list({ email: [email] });
  const customers = await customerCollection.next();
  return customers[0]?.id ?? null;
}

export async function createCustomerPortalUrl(
  customerId: string,
  subscriptionId?: string | null,
): Promise<string> {
  const paddle = getPaddleServerClient();
  if (!paddle) {
    throw new Error("Paddle sandbox API key is not configured");
  }

  let subscriptionIds: string[];
  if (subscriptionId) {
    subscriptionIds = [subscriptionId];
  } else {
    const subscriptionCollection = paddle.subscriptions.list({ customerId: [customerId] });
    const subscriptions = await subscriptionCollection.next();
    subscriptionIds = subscriptions.map((subscription) => subscription.id);
  }

  const session = await paddle.customerPortalSessions.create(customerId, subscriptionIds);

  const updatePaymentUrl = session.urls.subscriptions[0]?.updateSubscriptionPaymentMethod;
  if (updatePaymentUrl) {
    return updatePaymentUrl;
  }

  return session.urls.general.overview;
}
