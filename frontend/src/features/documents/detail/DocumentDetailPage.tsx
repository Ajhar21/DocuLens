import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowLeft,
  FileQuestion,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchDocumentDetail } from "@/features/documents/api";
import { isDocumentTerminal } from "@/features/documents/status";
import { usePolling } from "@/hooks/usePolling";
import { ApiError } from "@/lib/api/errors";
import { ExtractedInvoiceCard } from "./ExtractedInvoiceCard";
import { HeaderCard } from "./HeaderCard";
import { ProcessingCard } from "./ProcessingCard";
import { ValidationCard } from "./ValidationCard";

export function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();

  const {
    data: document,
    error,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["document", id],
    queryFn: () => {
      if (!id) throw new Error("Document ID is required");
      return fetchDocumentDetail(id);
    },
    enabled: Boolean(id),
  });

  const isTerminal = isDocumentTerminal(document);

  const { isConnectionIssue, restart } = usePolling({
    callback: async () => {
      const res = await refetch();
      return res.data;
    },
    intervalMs: 3000,
    backoffIntervalMs: 10000,
    maxConsecutiveErrors: 3,
    stopWhen: (doc) => isDocumentTerminal(doc),
    enabled: Boolean(document) && !isTerminal,
  });

  const handleJobTriggered = () => {
    void refetch();
    restart();
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-2">
          <Skeleton className="h-8 w-32" />
        </div>
        <DetailLoadingSkeleton />
      </div>
    );
  }

  if (error) {
    if (error instanceof ApiError) {
      if (error.kind === "not_found" || error.status === 404) {
        return (
          <div className="space-y-4">
            <BackNavigation />
            <Card className="border shadow-sm">
              <CardContent className="flex flex-col items-center justify-center py-16 text-center">
                <FileQuestion className="h-12 w-12 text-muted-foreground/60" />
                <h2 className="mt-4 text-lg font-semibold">Document Not Found</h2>
                <p className="mt-1 max-w-sm text-xs text-muted-foreground">
                  The requested document could not be located. It may have been deleted or the identifier is invalid.
                </p>
                <Button asChild variant="outline" size="sm" className="mt-6">
                  <Link to="/documents">Back to Documents</Link>
                </Button>
              </CardContent>
            </Card>
          </div>
        );
      }

      if (error.kind === "forbidden" || error.status === 403) {
        return (
          <div className="space-y-4">
            <BackNavigation />
            <Card className="border shadow-sm">
              <CardContent className="flex flex-col items-center justify-center py-16 text-center">
                <ShieldAlert className="h-12 w-12 text-destructive/70" />
                <h2 className="mt-4 text-lg font-semibold">Access Denied</h2>
                <p className="mt-1 max-w-sm text-xs text-muted-foreground">
                  You do not have the required permissions to view this document.
                </p>
                <Button asChild variant="outline" size="sm" className="mt-6">
                  <Link to="/documents">Back to Documents</Link>
                </Button>
              </CardContent>
            </Card>
          </div>
        );
      }
    }

    return (
      <div className="space-y-4">
        <BackNavigation />
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Failed to load document details</AlertTitle>
          <AlertDescription className="mt-1 flex items-center justify-between text-xs">
            <span>{error instanceof Error ? error.message : "An unexpected error occurred."}</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void refetch()}
              className="h-7 gap-1.5 bg-background text-xs text-foreground hover:bg-accent"
            >
              <RefreshCw className="h-3 w-3" />
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!document) {
    return (
      <div className="space-y-4">
        <BackNavigation />
        <Card>
          <CardContent className="py-12 text-center text-xs text-muted-foreground">
            No document data returned.
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-12">
      {/* Navigation */}
      <BackNavigation />

      {/* 1. Header Card */}
      <CardBoundary name="Document Header">
        <HeaderCard document={document} />
      </CardBoundary>

      {/* 2. Processing Pipeline Card */}
      <CardBoundary name="Processing Pipeline">
        <ProcessingCard
          document={document}
          isConnectionIssue={isConnectionIssue}
          onJobTriggered={handleJobTriggered}
        />
      </CardBoundary>

      {/* 3. Extracted Invoice Card */}
      <CardBoundary name="Extracted Invoice">
        <ExtractedInvoiceCard document={document} />
      </CardBoundary>

      {/* 4. Validation Rules Card */}
      <CardBoundary name="Validation Rules">
        <ValidationCard document={document} />
      </CardBoundary>
    </div>
  );
}

function BackNavigation() {
  return (
    <div className="flex items-center">
      <Button
        asChild
        variant="ghost"
        size="sm"
        className="-ml-2 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
      >
        <Link to="/documents">
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Back to documents</span>
        </Link>
      </Button>
    </div>
  );
}

function DetailLoadingSkeleton() {
  return (
    <div className="space-y-6">
      {/* Header Skeleton */}
      <Card className="border shadow-sm">
        <CardHeader className="space-y-2">
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-4 w-1/4" />
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        </CardContent>
      </Card>

      {/* Processing Skeleton */}
      <Card className="border shadow-sm">
        <CardHeader>
          <Skeleton className="h-5 w-40" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-28 w-full" />
        </CardContent>
      </Card>

      {/* Extracted Invoice Skeleton */}
      <Card className="border shadow-sm">
        <CardHeader>
          <Skeleton className="h-5 w-48" />
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>

      {/* Validation Skeleton */}
      <Card className="border shadow-sm">
        <CardHeader>
          <Skeleton className="h-5 w-40" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * Isolated card boundary to ensure an issue with a single card does not blank the page.
 */
function CardBoundary({
  name,
  children,
}: {
  name: string;
  children: React.ReactNode;
}) {
  try {
    return <>{children}</>;
  } catch (err) {
    return (
      <Card className="border border-destructive/30 bg-destructive/5 p-4 text-xs">
        <p className="font-semibold text-destructive">Failed to render {name}</p>
        <p className="mt-1 text-muted-foreground">
          {err instanceof Error ? err.message : "Render error occurred."}
        </p>
      </Card>
    );
  }
}

