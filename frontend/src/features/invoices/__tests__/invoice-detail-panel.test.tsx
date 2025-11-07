import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { components } from "@/api/types";

vi.mock("../use-invoice-detail", () => ({
  useInvoiceDetail: vi.fn(),
}));

vi.mock("../use-update-invoice-status", () => ({
  useUpdateInvoiceStatus: vi.fn(),
}));

import { InvoiceDetailPanel } from "../invoice-detail";
import { useInvoiceDetail } from "../use-invoice-detail";
import { useUpdateInvoiceStatus } from "../use-update-invoice-status";

const mockUseInvoiceDetail = vi.mocked(useInvoiceDetail);
const mockUseUpdateInvoiceStatus = vi.mocked(useUpdateInvoiceStatus);

type InvoiceDetail = components["schemas"]["InvoiceOutDetailed"];

describe("InvoiceDetailPanel", () => {
  beforeEach(() => {
    mockUseInvoiceDetail.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useInvoiceDetail>);

    mockUseUpdateInvoiceStatus.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useUpdateInvoiceStatus>);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("prompts the user to select an invoice when none is active", () => {
    render(<InvoiceDetailPanel invoiceId={null} />);
    expect(
      screen.getByText(/Select an invoice to see full details/i)
    ).toBeInTheDocument();
  });

  it("renders invoice metadata and updates status", async () => {
    const invoice: InvoiceDetail = {
      invoice_id: "INV-100",
      amount: "5000",
      status: "pending",
      pdf_url: null,
      created_at: "2025-10-17T10:00:00Z",
      due_date: null,
      discount_amount: null,
      customer: { name: "Detail Customer", phone: "+2347000000000" },
      lines: [
        {
          id: 1,
          description: "Consulting",
          quantity: 2,
          unit_price: "2500",
        },
      ],
    };

    mockUseInvoiceDetail.mockReturnValue({
      data: invoice,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useInvoiceDetail>);

    const mutate = vi.fn();
    mockUseUpdateInvoiceStatus.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useUpdateInvoiceStatus>);

    render(<InvoiceDetailPanel invoiceId="INV-100" />);

    expect(screen.getByText(/Invoice INV-100/)).toBeInTheDocument();
    expect(screen.getByText(/Consulting/)).toBeInTheDocument();

    const select = screen.getByRole("combobox");
    await userEvent.selectOptions(select, "paid");

    expect(mutate).toHaveBeenCalledWith("paid");
  });
});
