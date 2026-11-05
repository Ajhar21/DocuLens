import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Eye,
  FileText,
  Filter,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "@/features/documents/StatusBadge";
import { formatCurrency, formatDateTime } from "@/lib/format";
import { fetchReviewQueue } from "./api";

const PAGE_SIZE = 20;

export function ReviewQueuePage() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const offset = (page - 1) * PAGE_SIZE;

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["reviews", { limit: PAGE_SIZE, offset, statusFilter }],
    queryFn: () =>
      fetchReviewQueue({
        limit: PAGE_SIZE,
        offset,
        review_status: statusFilter === "all" ? undefined : statusFilter,
      }),
  });

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const items = data?.items ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Review Queue
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Inspect, correct, and verify extracted invoice headers and financial validations.
          </p>
        </div>

        {/* Filter Toolbar */}
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <label htmlFor="review-status-filter" className="sr-only">
            Filter by review status
          </label>
          <select
            id="review-status-filter"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="flex h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <option value="all">All Review Statuses</option>
            <option value="needs_review">Needs Review</option>
            <option value="pending">Pending</option>
            <option value="in_review">In Review</option>
            <option value="corrected">Corrected</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
      </div>

      {/* Main Content */}
      <Card className="border shadow-sm">
        <CardHeader className="border-b py-3 px-6">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold text-muted-foreground">
              {isLoading
                ? "Loading reviews…"
                : `Showing ${items.length} of ${total} documents`}
            </CardTitle>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          {isLoading && <LoadingState message="Loading review queue…" className="m-6" />}

          {isError && (
            <div className="p-6">
              <ErrorState
                title="Failed to Load Review Queue"
                message={error instanceof Error ? error.message : "An unexpected error occurred."}
                onRetry={() => void refetch()}
              />
            </div>
          )}

          {!isLoading && !isError && items.length === 0 && (
            <div className="p-6">
              <EmptyState
                icon={ClipboardCheck}
                title="Review Queue Empty"
                description={
                  statusFilter !== "all"
                    ? `No documents found with review status '${statusFilter}'.`
                    : "There are currently no documents requiring human review."
                }
                action={
                  statusFilter !== "all" ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setStatusFilter("all")}
                    >
                      Clear Filter
                    </Button>
                  ) : undefined
                }
              />
            </div>
          )}

          {!isLoading && !isError && items.length > 0 && (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/40 hover:bg-muted/40">
                    <TableHead className="w-[220px]">Document</TableHead>
                    <TableHead>Supplier</TableHead>
                    <TableHead>Invoice No.</TableHead>
                    <TableHead className="text-right">Total Amount</TableHead>
                    <TableHead>Review Status</TableHead>
                    <TableHead>Validation Issues</TableHead>
                    <TableHead>Uploaded By</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((item) => {
                    const hasIssues = item.error_count > 0 || item.warning_count > 0;
                    return (
                      <TableRow
                        key={item.id}
                        className="cursor-pointer transition-colors hover:bg-muted/30"
                        onClick={() => navigate(`/review/${item.id}`)}
                      >
                        <TableCell className="font-medium">
                          <div className="flex items-center gap-2">
                            <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                            <span
                              className="max-w-[180px] truncate"
                              title={item.original_filename}
                            >
                              {item.original_filename}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell>
                          <span
                            className="max-w-[140px] truncate block"
                            title={item.supplier_name || "—"}
                          >
                            {item.supplier_name || "—"}
                          </span>
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {item.invoice_number || "—"}
                        </TableCell>
                        <TableCell className="text-right font-medium">
                          {item.total != null
                            ? formatCurrency(item.total, item.currency)
                            : "—"}
                        </TableCell>
                        <TableCell>
                          <StatusBadge
                            status={item.review_status}
                            category="review"
                          />
                        </TableCell>
                        <TableCell>
                          {hasIssues ? (
                            <div className="flex items-center gap-1.5">
                              {item.error_count > 0 && (
                                <Badge
                                  variant="destructive"
                                  className="h-5 px-1.5 text-[10px] gap-1"
                                >
                                  <AlertCircle className="h-3 w-3" />
                                  <span>{item.error_count}</span>
                                </Badge>
                              )}
                              {item.warning_count > 0 && (
                                <Badge
                                  variant="outline"
                                  className="h-5 border-amber-500/40 bg-amber-50 text-amber-800 text-[10px] gap-1 dark:bg-amber-950/40 dark:text-amber-300"
                                >
                                  <AlertTriangle className="h-3 w-3" />
                                  <span>{item.warning_count}</span>
                                </Badge>
                              )}
                            </div>
                          ) : (
                            <span className="text-xs text-muted-foreground">None</span>
                          )}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {item.uploader?.full_name || "System"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                          {formatDateTime(item.created_at)}
                        </TableCell>
                        <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                          <Button
                            asChild
                            variant="ghost"
                            size="sm"
                            className="h-8 gap-1.5 text-xs text-primary"
                          >
                            <Link to={`/review/${item.id}`}>
                              <Eye className="h-3.5 w-3.5" />
                              <span>Review</span>
                            </Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>

        {/* Pagination Footer */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t px-6 py-3">
            <p className="text-xs text-muted-foreground">
              Page {page} of {totalPages}
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="h-8 w-8 p-0"
              >
                <ChevronLeft className="h-4 w-4" />
                <span className="sr-only">Previous page</span>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="h-8 w-8 p-0"
              >
                <ChevronRight className="h-4 w-4" />
                <span className="sr-only">Next page</span>
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

