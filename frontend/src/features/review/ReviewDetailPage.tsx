import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingState } from "@/components/shared/LoadingState";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/features/documents/StatusBadge";
import { ApiError } from "@/lib/api/errors";
import type { CorrectionItem } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { usePermissions } from "@/lib/permissions";
import {
  approveDocument,
  fetchReviewDetail,
  rejectDocument,
  submitCorrections,
} from "./api";
import { ApproveDialog, RejectDialog } from "./ApproveRejectDialogs";
import { CorrectionHistoryPanel } from "./CorrectionHistoryPanel";
import { DocumentPreview } from "./DocumentPreview";
import { HeaderCorrectionForm } from "./HeaderCorrectionForm";
import { ReadOnlyLineItems } from "./ReadOnlyLineItems";

export function ReviewDetailPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const queryClient = useQueryClient();
  const { can } = usePermissions();

  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);

  const canEdit = can("extraction:edit");
  const canApprove = can("correction:approve");

  const queryKey = ["review", documentId];

  const {
    data: detail,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey,
    queryFn: () => {
      if (!documentId) throw new Error("Document ID required");
      return fetchReviewDetail(documentId);
    },
    enabled: Boolean(documentId),
  });

  const invalidateAll = () => {
    void queryClient.invalidateQueries({ queryKey });
    void queryClient.invalidateQueries({ queryKey: ["reviews"] });
    void queryClient.invalidateQueries({ queryKey: ["document", documentId] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
  };

  const handleMutationError = (err: unknown, defaultMsg: string) => {
    if (err instanceof ApiError) {
      if (err.status === 403) {
        toast.error("Permission denied: You do not have permission to perform this action.");
        return;
      }
      if (err.status === 409) {
        toast.error(`Conflict: ${err.message}`);
        void refetch();
        return;
      }
      if (err.status === 422) {
        toast.error(`Validation error: ${err.message}`);
        return;
      }
      toast.error(err.message || defaultMsg);
      return;
    }
    toast.error(err instanceof Error ? err.message : defaultMsg);
  };

  const correctionsMutation = useMutation({
    mutationFn: (items: CorrectionItem[]) => {
      if (!documentId) throw new Error("Document ID required");
      return submitCorrections(documentId, items);
    },
    onSuccess: (updated) => {
      toast.success("Corrections saved successfully.");
      queryClient.setQueryData(queryKey, updated);
      invalidateAll();
    },
    onError: (err) => handleMutationError(err, "Failed to submit corrections."),
  });

  const approveMutation = useMutation({
    mutationFn: (notes?: string) => {
      if (!documentId) throw new Error("Document ID required");
      return approveDocument(documentId, notes);
    },
    onSuccess: (updated) => {
      toast.success("Invoice approved and locked.");
      setApproveOpen(false);
      queryClient.setQueryData(queryKey, updated);
      invalidateAll();
    },
    onError: (err) => handleMutationError(err, "Failed to approve document."),
  });

  const rejectMutation = useMutation({
    mutationFn: (reason: string) => {
      if (!documentId) throw new Error("Document ID required");
      return rejectDocument(documentId, reason);
    },
    onSuccess: (updated) => {
      toast.warning("Invoice rejected and reopened for review.");
      setRejectOpen(false);
      queryClient.setQueryData(queryKey, updated);
      invalidateAll();
    },
    onError: (err) => handleMutationError(err, "Failed to reject document."),
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link to="/review">
              <ArrowLeft className="h-4 w-4 mr-1" />
              <span>Back to Queue</span>
            </Link>
          </Button>
        </div>
        <LoadingState message="Loading review detail and document preview…" lines={6} />
      </div>
    );
  }

  if (isError || !detail) {
    const isForbidden = error instanceof ApiError && error.status === 403;
    return (
      <div className="space-y-6">
        <Button asChild variant="ghost" size="sm">
          <Link to="/review">
            <ArrowLeft className="h-4 w-4 mr-1" />
            <span>Back to Queue</span>
          </Link>
        </Button>
        <ErrorState
          isForbidden={isForbidden}
          title={isForbidden ? "Access Denied" : "Failed to Load Review"}
          message={error instanceof Error ? error.message : "Document review detail could not be loaded."}
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  const isApproved = detail.review_status === "approved";
  const validationResults = detail.validation_results || [];

  // Document-level issues (where field_name is null or document-level e.g. duplicate)
  const docLevelIssues = validationResults.filter(
    (v) =>
      !v.field_name && (v.status === "FAILED" || v.status === "SKIPPED"),
  );

  return (
    <div className="space-y-6">
      {/* Top Navigation & Status Bar */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b pb-4">
        <div className="flex items-center gap-3">
          <Button asChild variant="outline" size="sm" className="h-8 gap-1.5">
            <Link to="/review">
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Back to Queue</span>
            </Link>
          </Button>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-foreground truncate max-w-md">
              {detail.original_filename}
            </h1>
            <p className="text-xs text-muted-foreground">
              Uploaded by {detail.uploader?.full_name || "System"} on {formatDateTime(detail.created_at)}
            </p>
          </div>
        </div>

        {/* Status & Review Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={detail.review_status} category="review" />

          {/* Action buttons gated by permission */}
          {canApprove && !isApproved && (
            <Button
              size="sm"
              onClick={() => setApproveOpen(true)}
              className="h-8 gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              <span>Approve</span>
            </Button>
          )}

          {canApprove && (
            <Button
              variant={isApproved ? "outline" : "destructive"}
              size="sm"
              onClick={() => setRejectOpen(true)}
              className="h-8 gap-1.5 text-xs"
            >
              <XCircle className="h-3.5 w-3.5" />
              <span>{isApproved ? "Reopen / Reject" : "Reject"}</span>
            </Button>
          )}
        </div>
      </div>

      {/* Document-level Validation Issues Banner */}
      {docLevelIssues.length > 0 && (
        <div className="space-y-2">
          {docLevelIssues.map((issue) => {
            const isError = issue.severity === "ERROR";
            return (
              <Alert
                key={issue.id}
                variant={isError ? "destructive" : "default"}
                className={!isError ? "border-amber-500/40 bg-amber-50/50 text-amber-900 dark:bg-amber-950/20 dark:text-amber-300" : undefined}
              >
                {isError ? (
                  <AlertCircle className="h-4 w-4" />
                ) : (
                  <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
                )}
                <AlertTitle className="text-xs font-semibold flex items-center gap-2">
                  <span>Document Validation {isError ? "Error" : "Warning"}</span>
                  <Badge variant="outline" className="text-[10px] font-mono h-4">
                    {issue.validation_code}
                  </Badge>
                </AlertTitle>
                <AlertDescription className="text-xs mt-1 space-y-1">
                  <p>{issue.message}</p>
                  {(issue.expected_value || issue.actual_value) && (
                    <div className="flex gap-4 text-[11px] font-mono text-muted-foreground pt-1">
                      {issue.expected_value && (
                        <span>Expected: <strong>{issue.expected_value}</strong></span>
                      )}
                      {issue.actual_value && (
                        <span>Actual: <strong>{issue.actual_value}</strong></span>
                      )}
                    </div>
                  )}
                </AlertDescription>
              </Alert>
            );
          })}
        </div>
      )}

      {/* Two-Pane Layout: Left = Document Preview, Right = Header Form, Line Items, History */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 items-start">
        {/* Left Pane: Document Preview */}
        <div className="lg:col-span-6 h-[720px] sticky top-4">
          <DocumentPreview
            documentId={detail.document_id}
            filename={detail.original_filename}
          />
        </div>

        {/* Right Pane: Header Form, Line Items, Correction History */}
        <div className="lg:col-span-6 space-y-6">
          <HeaderCorrectionForm
            extractedInvoice={detail.extracted_invoice}
            originalLlmOutput={detail.original_llm_output}
            validationResults={validationResults}
            isApproved={isApproved}
            canEdit={canEdit}
            isSubmitting={correctionsMutation.isPending}
            onSubmitCorrections={async (items) => {
              await correctionsMutation.mutateAsync(items);
            }}
          />

          <ReadOnlyLineItems
            lineItems={detail.extracted_invoice?.line_items}
            currency={detail.extracted_invoice?.currency}
          />

          <CorrectionHistoryPanel corrections={detail.corrections} />
        </div>
      </div>

      {/* Dialogs */}
      <ApproveDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        onConfirm={async (notes) => {
          await approveMutation.mutateAsync(notes);
        }}
        isSubmitting={approveMutation.isPending}
      />

      <RejectDialog
        open={rejectOpen}
        onOpenChange={setRejectOpen}
        onConfirm={async (reason) => {
          await rejectMutation.mutateAsync(reason);
        }}
        isSubmitting={rejectMutation.isPending}
      />
    </div>
  );
}
