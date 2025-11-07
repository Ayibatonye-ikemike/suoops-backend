import type {
  BankDetailsOut,
  BankDetailsUpdate,
  BankFormState,
} from "./bank-details-form.types";

export const formatAccountNumber = (value: string) =>
  value.replace(/(\d{4})(?=\d)/g, "$1 ").trim();

export const toPayload = (state: BankFormState): BankDetailsUpdate => ({
  business_name: state.businessName || null,
  bank_name: state.bankName || null,
  account_number: state.accountNumber || null,
  account_name: state.accountName || null,
});

export const toFormState = (
  details: BankDetailsOut | undefined,
): BankFormState => ({
  businessName: details?.business_name ?? "",
  bankName: details?.bank_name ?? "",
  accountNumber: details?.account_number ?? "",
  accountName: details?.account_name ?? "",
});

export const getErrorMessage = (err: unknown) => {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  return "Something went wrong. Please try again.";
};
