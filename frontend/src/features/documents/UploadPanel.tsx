import { forwardRef, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Loader2,
  RotateCcw,
  Trash2,
  Upload,
  X,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { BatchUploadResponse } from "@/lib/api/types";
import { formatBytes } from "@/lib/format";
import { Dropzone } from "./Dropzone";
import { precheckFile } from "./file-precheck";
import { useUploadDocumentsMutation, useUploadPolicy } from "./queries";

interface QueuedFileEntry {
  id: string;
  file: File;
}

export const UploadPanel = forwardRef<HTMLButtonElement>(
  function UploadPanel(_props, dropzoneRef) {
    const { data: policy } = useUploadPolicy();
    const uploadMutation = useUploadDocumentsMutation();

    const [selectedEntries, setSelectedEntries] = useState<QueuedFileEntry[]>([]);
    const [progressPct, setProgressPct] = useState<number>(0);
    const [lastBatchResult, setLastBatchResult] =
      useState<BatchUploadResponse | null>(null);
    const abortControllerRef = useRef<AbortController | null>(null);

    const activePolicy = policy!;
    const isUploading = uploadMutation.isPending;

    const handleFilesSelected = (incomingFiles: File[]) => {
      setLastBatchResult(null);
      setSelectedEntries((prev) => {
        const next = [...prev];
        for (const file of incomingFiles) {
          const id = `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2, 7)}`;
          next.push({ id, file });
        }
        return next;
      });
    };

    const handleRemoveEntry = (id: string) => {
      setSelectedEntries((prev) => prev.filter((item) => item.id !== id));
    };

    const handleClearSelection = () => {
      setSelectedEntries([]);
    };

    const handleStartUpload = async () => {
      if (selectedEntries.length === 0 || isUploading) return;

      const controller = new AbortController();
      abortControllerRef.current = controller;
      setProgressPct(0);
      setLastBatchResult(null);

      try {
        const batchResult = await uploadMutation.mutateAsync({
          files: selectedEntries.map((entry) => entry.file),
          onProgress: (pct) => setProgressPct(pct),
          signal: controller.signal,
        });
        setLastBatchResult(batchResult);
        setSelectedEntries([]);
      } catch {
        // Error toast is already handled by `useUploadDocumentsMutation`.
      } finally {
        abortControllerRef.current = null;
      }
    };

    const handleCancelUpload = () => {
      abortControllerRef.current?.abort();
    };

    const warningCount = selectedEntries.reduce((acc, entry) => {
      const check = precheckFile(entry.file, activePolicy);
      return acc + (check.valid ? 0 : 1);
    }, 0);

    return (
      <Card data-testid="upload-panel">
        <CardHeader className="pb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base font-semibold">
                Upload documents
              </CardTitle>
              <CardDescription className="mt-1">
                Select one or more files to validate and queue for background
                parsing.
              </CardDescription>
            </div>
            {lastBatchResult && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setLastBatchResult(null)}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Dismiss results
              </Button>
            )}
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          <Dropzone
            ref={dropzoneRef}
            policy={activePolicy}
            disabled={isUploading}
            onFilesSelected={handleFilesSelected}
          />

          {/* Selected files staged for upload */}
          {selectedEntries.length > 0 && (
            <div
              className="space-y-3 rounded-lg border bg-background p-4"
              data-testid="staged-files-list"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <span>
                    {selectedEntries.length}{" "}
                    {selectedEntries.length === 1 ? "file" : "files"} selected
                  </span>
                  {warningCount > 0 && (
                    <Badge
                      variant="outline"
                      className="border-amber-500/40 bg-amber-50 text-amber-800"
                    >
                      <AlertTriangle className="h-3 w-3" />
                      {warningCount} pre-check{" "}
                      {warningCount === 1 ? "warning" : "warnings"}
                    </Badge>
                  )}
                </div>

                {!isUploading && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={handleClearSelection}
                    className="h-7 px-2 text-xs text-muted-foreground"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Clear all
                  </Button>
                )}
              </div>

              <ul className="divide-y rounded-md border">
                {selectedEntries.map((entry) => {
                  const check = precheckFile(entry.file, activePolicy);
                  return (
                    <li
                      key={entry.id}
                      className="flex items-start justify-between gap-3 px-3 py-2.5 text-sm"
                    >
                      <div className="flex min-w-0 flex-1 items-start gap-2.5">
                        <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="truncate font-medium text-foreground">
                              {entry.file.name}
                            </span>
                            <span className="text-xs tabular-nums text-muted-foreground">
                              {formatBytes(entry.file.size)}
                            </span>
                          </div>
                          {check.warning && (
                            <p
                              className="mt-1 flex items-center gap-1.5 text-xs text-amber-700"
                              data-testid="precheck-warning"
                            >
                              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                              <span>Client pre-check: {check.warning}</span>
                            </p>
                          )}
                        </div>
                      </div>

                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        disabled={isUploading}
                        onClick={() => handleRemoveEntry(entry.id)}
                        className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
                        aria-label={`Remove ${entry.file.name}`}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </li>
                  );
                })}
              </ul>

              {isUploading ? (
                <div
                  className="space-y-2 pt-1"
                  aria-live="polite"
                  data-testid="upload-progress-area"
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-2 font-medium text-foreground">
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                      Uploading batch…
                    </span>
                    <span className="tabular-nums text-muted-foreground">
                      {progressPct}%
                    </span>
                  </div>
                  <Progress value={progressPct} aria-label="Upload progress" />
                  <div className="flex justify-end pt-1">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleCancelUpload}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-end gap-2 pt-1">
                  <Button
                    type="button"
                    onClick={handleStartUpload}
                    data-testid="submit-upload-button"
                  >
                    <Upload className="h-4 w-4" />
                    Upload {selectedEntries.length}{" "}
                    {selectedEntries.length === 1 ? "file" : "files"}
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* Per-file batch upload results (accepted vs rejected with server reason) */}
          {lastBatchResult && (
            <div
              className="space-y-3 rounded-lg border bg-muted/20 p-4"
              role="region"
              aria-label="Batch upload results"
              data-testid="batch-upload-results"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-semibold text-foreground">
                  Batch upload summary
                </p>
                <div className="flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className="border-status-parsed/30 bg-status-parsed-bg text-status-parsed"
                    data-testid="accepted-count-badge"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    {lastBatchResult.accepted_count} accepted
                  </Badge>
                  {lastBatchResult.rejected_count > 0 && (
                    <Badge
                      variant="outline"
                      className="border-status-failed/30 bg-status-failed-bg text-status-failed"
                      data-testid="rejected-count-badge"
                    >
                      <XCircle className="h-3.5 w-3.5" />
                      {lastBatchResult.rejected_count} rejected
                    </Badge>
                  )}
                </div>
              </div>

              <ul className="divide-y rounded-md border bg-background">
                {lastBatchResult.results.map((item, idx) => {
                  const isAccepted = item.status === "accepted";
                  return (
                    <li
                      key={`${item.filename}-${idx}`}
                      className="flex flex-col gap-1 px-3.5 py-3 text-sm sm:flex-row sm:items-center sm:justify-between"
                      data-testid={`batch-result-item-${item.status}`}
                    >
                      <div className="flex min-w-0 items-start gap-2.5">
                        {isAccepted ? (
                          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-status-parsed" />
                        ) : (
                          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-status-failed" />
                        )}
                        <div className="min-w-0">
                          <p className="truncate font-medium text-foreground">
                            {item.filename}
                          </p>
                          {isAccepted ? (
                            <p className="text-xs text-muted-foreground">
                              Accepted and queued for background extraction
                            </p>
                          ) : (
                            <p
                              className="text-xs font-medium text-status-failed"
                              data-testid="rejection-reason"
                            >
                              Rejected: {item.reason ?? "Rejected by server"}
                            </p>
                          )}
                        </div>
                      </div>

                      <Badge
                        variant="outline"
                        className={
                          isAccepted
                            ? "self-start border-status-parsed/30 bg-status-parsed-bg text-status-parsed sm:self-center"
                            : "self-start border-status-failed/30 bg-status-failed-bg text-status-failed sm:self-center"
                        }
                      >
                        {isAccepted ? "Accepted" : "Rejected"}
                      </Badge>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>
    );
  },
);

