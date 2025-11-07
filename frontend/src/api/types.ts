/**
 * Condensed API type surface derived from the service OpenAPI schema.
 * Regenerate via `npm run openapi` and keep this file under ~400 lines by curating
 * the exported types that the frontend uses directly.
 */

export type paths = Record<string, never>;
export type operations = Record<string, never>;
export type external = Record<string, never>;
export type $defs = Record<string, never>;

export interface components {
  schemas: {
    CustomerOut: {
      name: string;
      phone?: string | null;
    };
    HTTPValidationError: {
      detail?: components["schemas"]["ValidationError"][];
    };
    InvoiceCreate: {
      customer_name: string;
      customer_phone?: string | null;
      customer_email?: string | null;
      amount: number | string;
      due_date?: string | null;
      lines?: components["schemas"]["InvoiceLineIn"][] | null;
      discount_amount?: number | string | null;
    };
    InvoiceLineIn: {
      description: string;
      quantity: number;
      unit_price: number | string;
    };
    InvoiceLineOut: {
      id: number;
      description: string;
      quantity: number;
      unit_price: string;
    };
    InvoiceOut: {
      invoice_id: string;
      amount: string;
      status: string;
      pdf_url: string | null;
      created_at?: string | null;
      due_date?: string | null;
    };
    InvoiceOutDetailed: {
      invoice_id: string;
      amount: string;
      status: string;
      pdf_url: string | null;
      created_at?: string | null;
      due_date?: string | null;
      discount_amount?: string | null;
      customer?: components["schemas"]["CustomerOut"] | null;
      lines?: components["schemas"]["InvoiceLineOut"][];
    };
    InvoiceStatusUpdate: {
      status: "pending" | "awaiting_confirmation" | "paid" | "failed";
    };
    MessageOut: {
      detail: string;
    };
    InvoicePublicOut: {
      invoice_id: string;
      amount: string;
      status: "pending" | "awaiting_confirmation" | "paid" | "failed" | string;
      due_date?: string | null;
      customer_name?: string | null;
      business_name?: string | null;
      bank_name?: string | null;
      account_number?: string | null;
      account_name?: string | null;
    };
    RefreshRequest: {
      refresh_token?: string | null;
    };
    TokenOut: {
      access_token: string;
      token_type: string;
      access_expires_at: string;
      refresh_token?: string | null;
    };
    UserCreate: {
      phone: string;
      name: string;
      password: string;
    };
    UserLogin: {
      phone: string;
      password: string;
    };
    UserOut: {
      id: number;
      phone?: string | null;
      phone_verified?: boolean;
      email?: string | null;
      name: string;
      plan: string;  // FREE, STARTER, PRO, BUSINESS, ENTERPRISE
      invoices_this_month: number;
      logo_url?: string | null;
    };
    ValidationError: {
      loc: (string | number)[];
      msg: string;
      type: string;
    };
    WebhookEventOut: {
      provider: string;
      external_id: string;
      created_at: string;
    };
    BankDetailsUpdate: {
      business_name?: string | null;
      bank_name?: string | null;
      account_number?: string | null;
      account_name?: string | null;
    };
    BankDetailsOut: {
      business_name: string | null;
      bank_name: string | null;
      account_number: string | null;
      account_name: string | null;
      is_configured: boolean;
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}
