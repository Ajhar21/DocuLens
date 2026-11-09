import { useState } from "react";
import {
  Activity,
  AlertTriangle,
  Database,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { canReprocessDocuments } from "@/features/auth/roles";
import { useAuth } from "@/features/auth/use-auth";
import { reprocessDocument } from "@/features/documents/api";
import { StatusBadge } from "@/features/documents/StatusBadge";
import type { DocumentDetailRead, JobRead, JobType } from "@/lib/api/types";
import { formatDateTime, formatRelativeTime } from "@/lib/format";

interface ProcessingCardProps {
  document: DocumentDetailRead;
  isConnectionIssue?: boolean;
  onJobTriggered?: () => void;
}

const JOB_TYPE_LABELS: Record<string, string> = {
  parse: "Document Parsing",
  extraction: "Invoice Extraction",
  embedding: "Vector Indexing",
};

export function ProcessingCard({
  document: doc,
  isConnectionIssue = false,
  onJobTriggered,
}: ProcessingCardProps) {
  const { user } = useAuth();
  const canReprocess = user ? canReprocessDocuments(user.role) : false;

  const [confirmExtractionOpen, setConfirmExtractionOpen] = useState(false);
  const [reprocessingStage, setReprocessingStage] = useState<JobType | null>(null);

  const jobs = doc.processing_jobs || [];

  const extractionJob = jobs.find((j) => j.job_type === "extraction");
  const embeddingJob = jobs.find((j) => j.job_type === "embedding");

  const isExtractionActive =
    extractionJob?.status === "pending" || extractionJob?.status === "running";
  const isEmbeddingActive =
    embeddingJob?.status === "pending" || embeddingJob?.status === "running";

  const handleReprocess = async (stage: "extraction" | "embedding") => {
    try {
      setReprocessingStage(stage);
      await reprocessDocument(doc.id, stage);
      toast.success(
        `Enqueued ${stage === "extraction" ? "Extraction" : "Embedding"} job successfully.`,
      );
      onJobTriggered?.();
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Reprocessing failed. Please try again.";
      toast.error(message);
    } finally {
      setReprocessingStage(null);
      setConfirmExtractionOpen(false);
    }
  };

  return (
    <Card className="border shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2.5">
            <div className="rounded-md border bg-muted/30 p-2 text-primary">
              <Activity className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <CardTitle className="text-lg font-semibold">Processing Pipeline</CardTitle>
              <CardDescription className="text-xs text-muted-foreground">
                Background worker jobs, stage transitions, and search indexing
              </CardDescription>
            </div>
          </div>

          {canReprocess && (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 text-xs font-medium"
                disabled={isExtractionActive || reprocessingStage !== null}
                onClick={() => setConfirmExtractionOpen(true)}
              >
                {reprocessingStage === "extraction" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
                <span>Re-run extraction</span>
              </Button>

              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 text-xs font-medium"
                disabled={isEmbeddingActive || reprocessingStage !== null}
                onClick={() => void handleReprocess("embedding")}
              >
                {reprocessingStage === "embedding" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Database className="h-3.5 w-3.5" />
                )}
                <span>Re-run embedding</span>
              </Button>
            </div>
          )}
        </div>

        {isConnectionIssue && (
          <div className="mt-2 flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-50 px-3 py-1.5 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>Connection issue detected. Re-trying status poll every 10 seconds...</span>
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Jobs Table */}
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="w-[180px] text-xs">Job Type</TableHead>
                <TableHead className="w-[130px] text-xs">Status</TableHead>
                <TableHead className="text-xs">Stage</TableHead>
                <TableHead className="w-[90px] text-xs">Attempts</TableHead>
                <TableHead className="w-[150px] text-xs">Started</TableHead>
                <TableHead className="w-[150px] text-xs">Completed</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-6 text-center text-xs text-muted-foreground">
                    No processing jobs recorded for this document.
                  </TableCell>
                </TableRow>
              ) : (
                jobs.map((job) => (
                  <JobTableRow key={job.id} job={job} />
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>

      {/* Confirmation Dialog for Re-run Extraction */}
      <Dialog open={confirmExtractionOpen} onOpenChange={setConfirmExtractionOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-amber-500" />
              <span>Confirm Invoice Re-extraction</span>
            </DialogTitle>
            <DialogDescription className="mt-2 text-xs text-muted-foreground leading-relaxed">
              Re-running the extraction job will re-parse the document text and
              <strong> overwrite existing extracted invoice fields and line items</strong>.
              Deterministic financial validations will be re-evaluated.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4 gap-2 sm:gap-0">
            <DialogClose asChild>
              <Button variant="outline" size="sm" type="button">
                Cancel
              </Button>
            </DialogClose>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => void handleReprocess("extraction")}
              disabled={reprocessingStage !== null}
            >
              {reprocessingStage === "extraction" && (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              )}
              Overwrite & Re-extract
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function JobTableRow({ job }: { job: JobRead }) {
  const errorMsg = job.error_message || job.last_error;
  const startedAt = job.started_at || job.created_at;
  const completedAt = job.completed_at || job.finished_at;

  return (
    <TableRow>
      <TableCell className="font-medium text-xs">
        {JOB_TYPE_LABELS[job.job_type] || job.job_type}
      </TableCell>
      <TableCell>
        <StatusBadge status={job.status} category="job" error={errorMsg} />
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {job.current_stage || "—"}
      </TableCell>
      <TableCell className="text-xs">
        <span className="font-medium">{job.attempt_count ?? job.attempts ?? 0}</span>
        <span className="text-muted-foreground"> / {job.max_attempts}</span>
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        <RelativeTimeWithTooltip isoDate={startedAt} />
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        <RelativeTimeWithTooltip isoDate={completedAt} />
      </TableCell>
    </TableRow>
  );
}

function RelativeTimeWithTooltip({ isoDate }: { isoDate: string | null | undefined }) {
  if (!isoDate) return <span>—</span>;

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-help underline decoration-dotted underline-offset-2">
            {formatRelativeTime(isoDate)}
          </span>
        </TooltipTrigger>
        <TooltipContent className="text-xs">
          {formatDateTime(isoDate)}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
