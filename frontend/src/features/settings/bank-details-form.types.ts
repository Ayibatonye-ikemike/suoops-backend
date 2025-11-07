import type { components } from "@/api/types";

export type BankDetailsUpdate = components["schemas"]["BankDetailsUpdate"];
export type BankDetailsOut = components["schemas"]["BankDetailsOut"];

export type BankFormState = {
  businessName: string;
  bankName: string;
  accountNumber: string;
  accountName: string;
};
