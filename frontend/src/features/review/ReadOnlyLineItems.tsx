import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { InvoiceLineItemRead } from "@/lib/api/types";
import { formatCurrency } from "@/lib/format";

interface ReadOnlyLineItemsProps {
  lineItems: InvoiceLineItemRead[] | undefined;
  currency: string | null | undefined;
}

export function ReadOnlyLineItems({ lineItems, currency }: ReadOnlyLineItemsProps) {
  const items = lineItems || [];

  return (
    <Card className="border shadow-sm">
      <CardHeader className="border-b px-5 py-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold">
            Extracted Line Items (Read Only)
          </CardTitle>
          <span className="text-xs text-muted-foreground">
            {items.length} item{items.length === 1 ? "" : "s"}
          </span>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {items.length === 0 ? (
          <div className="py-8 text-center text-xs text-muted-foreground">
            No line items extracted for this invoice.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="w-[60px] text-center">#</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                  <TableHead className="text-right">Unit Price</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item, idx) => (
                  <TableRow key={item.id || idx}>
                    <TableCell className="text-center font-mono text-xs text-muted-foreground">
                      {item.line_no || idx + 1}
                    </TableCell>
                    <TableCell className="text-xs font-medium">
                      {item.description || "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {item.quantity != null ? String(item.quantity) : "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {item.unit_price != null
                        ? formatCurrency(item.unit_price, currency)
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs font-semibold">
                      {item.amount != null
                        ? formatCurrency(item.amount, currency)
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

