import {
  AlertCircle,
  AlertTriangle,
  FileSpreadsheet,
  Receipt,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { DocumentDetailRead } from "@/lib/api/types";
import { formatMoney } from "@/lib/format";

interface ExtractedInvoiceCardProps {
  document: DocumentDetailRead;
}

export function ExtractedInvoiceCard({ document: doc }: ExtractedInvoiceCardProps) {
  const invoice = doc.extracted_invoice;
  const jobs = doc.processing_jobs || [];
  const extractionJob = jobs.find((j) => j.job_type === "extraction");

  // Discount and shipping can come from top-level or extraction_metadata
  const meta = (invoice?.extraction_metadata || {}) as Record<string, unknown>;
  const discountVal = invoice?.discount ?? meta.discount;
  const shippingVal = invoice?.shipping ?? meta.shipping;

  if (!invoice) {
    let reasonTitle = "No Extracted Invoice Available";
    let reasonDesc =
      "No invoice data has been extracted. This document may not contain extractable invoice fields or is of a different document type.";
    let iconVariant: "default" | "destructive" = "default";

    if (extractionJob?.status === "running") {
      reasonTitle = "Extraction in Progress";
      reasonDesc =
        "The invoice extraction pipeline is actively running. Results will populate automatically once complete.";
    } else if (extractionJob?.status === "pending") {
      reasonTitle = "Extraction Queued";
      reasonDesc =
        "Extraction is scheduled and awaiting an available background worker.";
    } else if (extractionJob?.status === "failed") {
      reasonTitle = "Extraction Failed";
      reasonDesc =
        extractionJob.error_message ||
        extractionJob.last_error ||
        "The extraction stage failed during processing.";
      iconVariant = "destructive";
    } else if (doc.status === "failed") {
      reasonTitle = "Document Processing Failed";
      reasonDesc = doc.error || "The document encountered a fatal processing error.";
      iconVariant = "destructive";
    }

    return (
      <Card className="border shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2.5">
            <div className="rounded-md border bg-muted/30 p-2 text-primary">
              <Receipt className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <CardTitle className="text-lg font-semibold">Extracted Invoice Data</CardTitle>
              <CardDescription className="text-xs text-muted-foreground">
                Read-only structured extraction
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Alert variant={iconVariant} className="bg-muted/10">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle className="text-sm font-semibold">{reasonTitle}</AlertTitle>
            <AlertDescription className="mt-1 text-xs text-muted-foreground">
              {reasonDesc}
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const currency = invoice.currency;

  return (
    <Card className="border shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2.5">
            <div className="rounded-md border bg-muted/30 p-2 text-primary">
              <Receipt className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <CardTitle className="text-lg font-semibold">Extracted Invoice Data</CardTitle>
              <CardDescription className="text-xs text-muted-foreground">
                Deterministic invoice extraction (Read-Only)
              </CardDescription>
            </div>
          </div>
          <Badge variant="outline" className="w-fit text-[11px] font-normal text-muted-foreground">
            Read-only mode
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Core Invoice Metadata Grid */}
        <div className="grid grid-cols-2 gap-4 rounded-lg border bg-muted/10 p-4 sm:grid-cols-4">
          <FieldBlock
            label="Invoice Number"
            value={invoice.invoice_number}
            required
          />
          <FieldBlock
            label="Invoice Date"
            value={invoice.invoice_date}
            required
          />
          <FieldBlock
            label="Supplier"
            value={invoice.supplier_name}
            required
          />
          <FieldBlock
            label="Customer"
            value={invoice.customer_name}
          />
          <FieldBlock
            label="Currency"
            value={currency}
          />
          <FieldBlock
            label="Subtotal"
            value={formatMoney(invoice.subtotal, currency)}
            isFormatted
            rawEmpty={invoice.subtotal === null || invoice.subtotal === undefined}
          />
          <FieldBlock
            label="Tax Amount"
            value={formatMoney(invoice.tax, currency)}
            isFormatted
            rawEmpty={invoice.tax === null || invoice.tax === undefined}
          />
          <FieldBlock
            label="Total Amount"
            value={formatMoney(invoice.total, currency)}
            isFormatted
            required
            rawEmpty={invoice.total === null || invoice.total === undefined}
          />

          {/* Discount (if present) */}
          {(discountVal !== undefined && discountVal !== null) && (
            <FieldBlock
              label="Discount"
              value={formatMoney(discountVal as string | number, currency)}
              isFormatted
            />
          )}

          {/* Shipping (if present) */}
          {(shippingVal !== undefined && shippingVal !== null) && (
            <FieldBlock
              label="Shipping"
              value={formatMoney(shippingVal as string | number, currency)}
              isFormatted
            />
          )}
        </div>

        {/* Line Items Table */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <h4 className="text-xs font-semibold uppercase tracking-wider text-foreground">
              Line Items ({invoice.line_items?.length || 0})
            </h4>
          </div>

          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="w-[60px] text-xs">#</TableHead>
                  <TableHead className="text-xs">Description</TableHead>
                  <TableHead className="w-[100px] text-right text-xs">Quantity</TableHead>
                  <TableHead className="w-[120px] text-right text-xs">Unit Price</TableHead>
                  <TableHead className="w-[130px] text-right text-xs">Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(!invoice.line_items || invoice.line_items.length === 0) ? (
                  <TableRow>
                    <TableCell
                      colSpan={5}
                      className="py-6 text-center text-xs text-muted-foreground"
                    >
                      No line items extracted.
                    </TableCell>
                  </TableRow>
                ) : (
                  invoice.line_items.map((item) => (
                    <TableRow key={item.id || item.line_no}>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {item.line_no}
                      </TableCell>
                      <TableCell className="text-xs font-medium">
                        {item.description || (
                          <span className="text-muted-foreground italic">No description</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs">
                        {item.quantity !== null && item.quantity !== undefined
                          ? String(item.quantity)
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs">
                        {item.unit_price !== null && item.unit_price !== undefined
                          ? formatMoney(item.unit_price, currency)
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs font-semibold">
                        {item.amount !== null && item.amount !== undefined
                          ? formatMoney(item.amount, currency)
                          : "—"}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface FieldBlockProps {
  label: string;
  value: string | number | null | undefined;
  required?: boolean;
  isFormatted?: boolean;
  rawEmpty?: boolean;
}

function FieldBlock({
  label,
  value,
  required = false,
  isFormatted = false,
  rawEmpty = false,
}: FieldBlockProps) {
  const isMissing = rawEmpty || value === null || value === undefined || value === "";

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {required && isMissing && (
          <span
            className="inline-flex items-center gap-0.5 rounded bg-amber-100 px-1 py-0.2 text-[10px] font-semibold text-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
            title="Required field is missing"
          >
            <AlertTriangle className="h-2.5 w-2.5" />
            Required
          </span>
        )}
      </div>

      {isMissing ? (
        <p className="text-xs italic text-muted-foreground">Not found</p>
      ) : isFormatted ? (
        <p className="font-mono text-sm font-semibold">{String(value)}</p>
      ) : (
        <p className="text-sm font-medium text-foreground truncate" title={String(value)}>
          {String(value)}
        </p>
      )}
    </div>
  );
}

