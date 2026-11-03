import { useState } from "react";
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  FileSpreadsheet,
  FileText,
  Image as ImageIcon,
  Inbox,
  RefreshCw,
  Upload,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { DocumentStatus } from "@/lib/api/types";
import { formatBytes, formatDateTime } from "@/lib/format";
import { useDocumentsQuery } from "./queries";
import { isNonFinalStatus } from "./status";
import { StatusBadge } from "./StatusBadge";

const PAGE_SIZE = 20;

const STATUS_FILTERS: readonly {
  label: string;
  value: DocumentStatus | "all";
}[] = [
  { label: "All", value: "all" },
  { label: "Uploaded", value: "uploaded" },
  { label: "Processing", value: "processing" },
  { label: "Parsed", value: "parsed" },
  { label: "Failed", value: "failed" },
];

function FileTypeIcon({ ext }: { ext: string }) {
  const clean = ext.toLowerCase();
  if (clean === ".png" || clean === ".jpg" || clean === ".jpeg") {
    return <ImageIcon className="h-4 w-4 shrink-0 text-muted-foreground" />;
  }
  if (clean === ".xlsx" || clean === ".csv") {
    return (
      <FileSpreadsheet className="h-4 w-4 shrink-0 text-muted-foreground" />
    );
  }
  return <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />;
}

function formatFileTypeLabel(ext: string): string {
  return ext.replace(/^\./, "").toUpperCase() || "FILE";
}

interface DocumentTableProps {
  canUpload: boolean;
  onFocusUpload?: () => void;
}

export function DocumentTable({
  canUpload,
  onFocusUpload,
}: DocumentTableProps) {
  const [pageIndex, setPageIndex] = useState(0);
  const [statusFilter, setStatusFilter] = useState<DocumentStatus | "all">(
    "all",
  );

  const offset = pageIndex * PAGE_SIZE;
  const { data, isLoading, isError, error, refetch, isFetching } =
    useDocumentsQuery({
      limit: PAGE_SIZE,
      offset,
      status: statusFilter === "all" ? undefined : statusFilter,
    });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const isPolling = items.some((doc) => isNonFinalStatus(doc.status));

  const handleFilterChange = (next: DocumentStatus | "all") => {
    setStatusFilter(next);
    setPageIndex(0);
  };

  return (
    <Card data-testid="documents-table-card">
      <CardHeader className="flex flex-col gap-4 space-y-0 border-b pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <CardTitle className="text-base font-semibold">
            All documents
          </CardTitle>
          {!isLoading && (
            <Badge variant="secondary" className="tabular-nums">
              {total}
            </Badge>
          )}
          {isPolling && (
            <span
              className="inline-flex items-center gap-1.5 text-xs font-medium text-status-processing"
              data-testid="live-polling-indicator"
            >
              <span className="h-2 w-2 animate-ping rounded-full bg-status-processing" />
              Auto-updating
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <div
            role="group"
            aria-label="Filter documents by status"
            className="flex flex-wrap items-center gap-1 rounded-lg border bg-muted/40 p-1"
          >
            {STATUS_FILTERS.map((filter) => {
              const active = statusFilter === filter.value;
              return (
                <button
                  key={filter.value}
                  type="button"
                  onClick={() => handleFilterChange(filter.value)}
                  className={
                    active
                      ? "rounded-md bg-background px-2.5 py-1 text-xs font-medium text-foreground shadow-sm transition-colors"
                      : "rounded-md px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                  }
                >
                  {filter.label}
                </button>
              );
            })}
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void refetch()}
            disabled={isFetching}
            aria-label="Refresh document list"
          >
            <RefreshCw
              className={
                isFetching ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"
              }
            />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        {isError ? (
          <div className="p-6" data-testid="documents-error-state">
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Unable to load documents</AlertTitle>
              <AlertDescription className="mt-2 flex flex-wrap items-center justify-between gap-3">
                <span>
                  {error instanceof Error
                    ? error.message
                    : "An unexpected error occurred while loading documents."}
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void refetch()}
                >
                  Retry
                </Button>
              </AlertDescription>
            </Alert>
          </div>
        ) : isLoading ? (
          <div
            className="divide-y"
            aria-busy="true"
            aria-label="Loading documents"
            data-testid="documents-loading-skeleton"
          >
            {Array.from({ length: 5 }).map((_, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between gap-4 px-4 py-3.5"
              >
                <div className="flex items-center gap-3">
                  <Skeleton className="h-4 w-4 rounded" />
                  <Skeleton className="h-4 w-48" />
                </div>
                <div className="flex items-center gap-6">
                  <Skeleton className="hidden h-4 w-12 sm:block" />
                  <Skeleton className="hidden h-4 w-16 md:block" />
                  <Skeleton className="h-5 w-20 rounded-md" />
                  <Skeleton className="hidden h-4 w-28 lg:block" />
                </div>
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          <div
            className="flex flex-col items-center justify-center px-6 py-14 text-center"
            data-testid="documents-empty-state"
          >
            <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full border bg-muted/40 text-muted-foreground">
              <Inbox className="h-5 w-5" />
            </div>
            <h3 className="text-sm font-semibold text-foreground">
              {statusFilter === "all"
                ? "No documents uploaded yet"
                : `No ${statusFilter} documents`}
            </h3>
            <p className="mt-1 max-w-sm text-xs text-muted-foreground">
              {statusFilter !== "all"
                ? "No documents match the selected status filter."
                : canUpload
                  ? "Upload a PDF, image, or spreadsheet above to start background extraction."
                  : "Documents uploaded by reviewers and administrators will appear here automatically."}
            </p>
            <div className="mt-4">
              {statusFilter !== "all" ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => handleFilterChange("all")}
                >
                  Clear status filter
                </Button>
              ) : canUpload && onFocusUpload ? (
                <Button type="button" size="sm" onClick={onFocusUpload}>
                  <Upload className="h-4 w-4" />
                  Select files to upload
                </Button>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void refetch()}
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  Check again
                </Button>
              )}
            </div>
          </div>
        ) : (
          <>
            <Table data-testid="documents-table">
              <TableHeader>
                <TableRow>
                  <TableHead>Filename</TableHead>
                  <TableHead className="hidden sm:table-cell">Type</TableHead>
                  <TableHead className="hidden md:table-cell">Size</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="hidden lg:table-cell">
                    Uploaded by
                  </TableHead>
                  <TableHead className="text-right">Uploaded at</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((doc) => (
                  <TableRow key={doc.id} data-testid="document-row">
                    <TableCell className="max-w-[200px] sm:max-w-[280px]">
                      <div className="flex items-start gap-2.5">
                        <div className="mt-0.5">
                          <FileTypeIcon ext={doc.file_ext} />
                        </div>
                        <div className="min-w-0">
                          <p
                            className="truncate font-medium text-foreground"
                            title={doc.original_filename}
                          >
                            {doc.original_filename}
                          </p>
                          <p className="mt-0.5 text-xs tabular-nums text-muted-foreground md:hidden">
                            {formatFileTypeLabel(doc.file_ext)} ·{" "}
                            {formatBytes(doc.size_bytes)}
                          </p>
                          {doc.status === "failed" && doc.error && (
                            <p className="mt-0.5 line-clamp-1 text-xs text-status-failed">
                              {doc.error}
                            </p>
                          )}
                        </div>
                      </div>
                    </TableCell>

                    <TableCell className="hidden sm:table-cell">
                      <Badge
                        variant="secondary"
                        className="font-mono text-[11px]"
                      >
                        {formatFileTypeLabel(doc.file_ext)}
                      </Badge>
                    </TableCell>

                    <TableCell className="hidden tabular-nums text-muted-foreground md:table-cell">
                      {formatBytes(doc.size_bytes)}
                    </TableCell>

                    <TableCell>
                      <StatusBadge status={doc.status} error={doc.error} />
                    </TableCell>

                    <TableCell className="hidden text-muted-foreground lg:table-cell">
                      {doc.uploader?.full_name ?? "—"}
                    </TableCell>

                    <TableCell className="whitespace-nowrap text-right text-xs tabular-nums text-muted-foreground">
                      <time dateTime={doc.created_at}>
                        {formatDateTime(doc.created_at)}
                      </time>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {/* Pagination bar */}
            {total > PAGE_SIZE && (
              <div className="flex items-center justify-between border-t px-4 py-3 text-xs text-muted-foreground">
                <span className="tabular-nums">
                  Showing {offset + 1}–{Math.min(offset + items.length, total)}{" "}
                  of {total}
                </span>
                <div className="flex items-center gap-2">
                  <span className="tabular-nums">
                    Page {pageIndex + 1} of {totalPages}
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={pageIndex === 0}
                    onClick={() => setPageIndex((p) => Math.max(0, p - 1))}
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                    Previous
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={pageIndex + 1 >= totalPages}
                    onClick={() => setPageIndex((p) => p + 1)}
                  >
                    Next
                    <ChevronRight className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

