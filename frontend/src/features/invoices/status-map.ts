export const invoiceStatusLabels: Record<string, { label: string; tone: "neutral" | "success" | "warning" | "danger" }> = {
  pending: { label: "Awaiting bank transfer", tone: "warning" },
  awaiting_confirmation: { label: "Awaiting your confirmation", tone: "warning" },
  paid: { label: "Paid", tone: "success" },
  failed: { label: "Closed without payment", tone: "danger" },
};

export const invoiceStatusHelpText: Record<string, string> = {
  pending: "Confirm the customer’s transfer, then mark as paid to send a receipt.",
  awaiting_confirmation: "Customer clicked ‘I’ve sent the transfer’. Check your bank and mark as paid once received.",
  paid: "Status updated manually after verifying the bank transfer.",
  failed: "Use this if the invoice will not be collected.",
};
