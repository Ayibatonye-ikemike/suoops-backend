import { apiClient } from "./client";

export interface InitializeSubscriptionResponse {
  authorization_url: string;
  access_code: string;
  reference: string;
  amount: number;
  plan: string;
}

export interface VerifySubscriptionResponse {
  status: string;
  message: string;
  old_plan?: string;
  new_plan?: string;
  amount_paid?: number;
}

/**
 * Initialize Paystack payment for subscription upgrade.
 */
export async function initializeSubscription(
  plan: string
): Promise<InitializeSubscriptionResponse> {
  const response = await apiClient.post("/subscriptions/initialize", null, {
    params: { plan },
  });
  return response.data;
}

/**
 * Verify subscription payment after Paystack redirect.
 */
export async function verifySubscription(
  reference: string
): Promise<VerifySubscriptionResponse> {
  const response = await apiClient.get(`/subscriptions/verify/${reference}`);
  return response.data;
}
