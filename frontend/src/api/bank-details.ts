import { apiClient } from "./client";
import type { components } from "./types";

type BankDetailsOut = components["schemas"]["BankDetailsOut"];
type BankDetailsUpdate = components["schemas"]["BankDetailsUpdate"];
type MessageOut = components["schemas"]["MessageOut"];

export async function getBankDetails(): Promise<BankDetailsOut> {
  const response = await apiClient.get<BankDetailsOut>("/users/me/bank-details");
  return response.data;
}

export async function updateBankDetails(data: BankDetailsUpdate): Promise<BankDetailsOut> {
  const response = await apiClient.patch<BankDetailsOut>("/users/me/bank-details", data);
  return response.data;
}

export async function deleteBankDetails(): Promise<MessageOut> {
  const response = await apiClient.delete<MessageOut>("/users/me/bank-details");
  return response.data;
}
