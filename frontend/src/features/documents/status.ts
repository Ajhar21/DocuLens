import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Info,
  Loader2,
  MinusCircle,
  Tag,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type {
  DocumentDetailRead,
  DocumentStatus,
  JobStatus,
  ReviewStatus,
  ValidationSeverity,
  ValidationStatus,
} from "@/lib/api/types";

export interface StatusPresentation {
  label: string;
  description?: string;
  icon: LucideIcon;
  spin?: boolean;
  badgeClassName: string;
}

/**
 * Real backend DocumentStatus (`uploaded`, `processing`, `parsed`, `failed`)
 */
export const DOCUMENT_STATUS_META: Record<DocumentStatus, StatusPresentation> = {
  uploaded: {
    label: "Uploaded",
    description: "Queued and waiting for processing",
    icon: Clock,
    badgeClassName:
      "border-status-uploaded/25 bg-status-uploaded-bg text-status-uploaded",
  },
  processing: {
    label: "Processing",
    description: "Active processing underway",
    icon: Loader2,
    spin: true,
    badgeClassName:
      "border-status-processing/25 bg-status-processing-bg text-status-processing",
  },
  parsed: {
    label: "Parsed",
    description: "Document extraction and validation complete",
    icon: CheckCircle2,
    badgeClassName:
      "border-status-parsed/25 bg-status-parsed-bg text-status-parsed",
  },
  failed: {
    label: "Failed",
    description: "Document processing failed",
    icon: XCircle,
    badgeClassName:
      "border-status-failed/25 bg-status-failed-bg text-status-failed",
  },
};

/**
 * Real backend ReviewStatus (`pending`, `needs_review`, `approved`, `rejected`, `not_required`)
 */
export const REVIEW_STATUS_META: Record<ReviewStatus, StatusPresentation> = {
  pending: {
    label: "Review Pending",
    description: "Awaiting reviewer evaluation",
    icon: Clock,
    badgeClassName:
      "border-slate-500/25 bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  },
  needs_review: {
    label: "Needs Review",
    description: "Flagged with validation issues requiring attention",
    icon: AlertTriangle,
    badgeClassName:
      "border-amber-500/30 bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300",
  },
  approved: {
    label: "Approved",
    description: "Verified and approved by reviewer",
    icon: CheckCircle2,
    badgeClassName:
      "border-emerald-500/30 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300",
  },
  rejected: {
    label: "Rejected",
    description: "Document rejected",
    icon: XCircle,
    badgeClassName:
      "border-rose-500/30 bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300",
  },
  not_required: {
    label: "Review Not Required",
    description: "Automated checks passed; manual review bypassed",
    icon: MinusCircle,
    badgeClassName:
      "border-zinc-500/25 bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  },
};

/**
 * Real backend JobStatus (`pending`, `running`, `succeeded`, `failed`)
 */
export const JOB_STATUS_META: Record<JobStatus, StatusPresentation> = {
  pending: {
    label: "Queued",
    description: "Job scheduled to run",
    icon: Clock,
    badgeClassName:
      "border-slate-500/25 bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  },
  running: {
    label: "Running",
    description: "Job is currently being executed by a worker",
    icon: Loader2,
    spin: true,
    badgeClassName:
      "border-sky-500/30 bg-sky-50 text-sky-800 dark:bg-sky-950/40 dark:text-sky-300",
  },
  succeeded: {
    label: "Succeeded",
    description: "Job completed successfully",
    icon: CheckCircle2,
    badgeClassName:
      "border-emerald-500/30 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300",
  },
  failed: {
    label: "Failed",
    description: "Job terminated with an error",
    icon: XCircle,
    badgeClassName:
      "border-rose-500/30 bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300",
  },
};

/**
 * Real backend ValidationSeverity (`ERROR`, `WARNING`, `INFO`)
 */
export const VALIDATION_SEVERITY_META: Record<ValidationSeverity, StatusPresentation> = {
  ERROR: {
    label: "Error",
    description: "Critical financial inconsistency or missing required field",
    icon: AlertCircle,
    badgeClassName:
      "border-rose-500/40 bg-rose-50 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300 font-semibold",
  },
  WARNING: {
    label: "Warning",
    description: "Potential discrepancy or duplicate invoice flag",
    icon: AlertTriangle,
    badgeClassName:
      "border-amber-500/40 bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300 font-medium",
  },
  INFO: {
    label: "Info",
    description: "Informational note or fallback observation",
    icon: Info,
    badgeClassName:
      "border-blue-500/40 bg-blue-50 text-blue-800 dark:bg-blue-950/50 dark:text-blue-300",
  },
};

/**
 * Real backend ValidationStatus (`PASSED`, `FAILED`, `SKIPPED`)
 */
export const VALIDATION_STATUS_META: Record<ValidationStatus, StatusPresentation> = {
  PASSED: {
    label: "Passed",
    description: "Validation check satisfied",
    icon: CheckCircle2,
    badgeClassName:
      "border-emerald-500/30 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300",
  },
  FAILED: {
    label: "Failed",
    description: "Validation rule failed",
    icon: XCircle,
    badgeClassName:
      "border-rose-500/30 bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300",
  },
  SKIPPED: {
    label: "Skipped",
    description: "Validation skipped due to missing prerequisite data",
    icon: MinusCircle,
    badgeClassName:
      "border-zinc-500/25 bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  },
};

/**
 * Human labels for all 11 backend deterministic validation codes
 */
export const VALIDATION_CODE_LABELS: Record<string, string> = {
  MISSING_REQUIRED_FIELD: "Missing Required Field",
  AMBIGUOUS_DATE: "Ambiguous Date Format",
  NO_LINE_ITEMS: "No Line Items Extracted",
  LINE_ITEM_AMOUNT_MISMATCH: "Line Item Amount Mismatch",
  SUBTOTAL_MISMATCH: "Subtotal Calculation Mismatch",
  TOTAL_MISMATCH: "Total Calculation Mismatch",
  NEGATIVE_AMOUNT: "Negative Amount Detected",
  FUTURE_DATE: "Future Invoice Date",
  UNKNOWN_CURRENCY: "Unknown or Ambiguous Currency",
  LOW_OCR_CONFIDENCE: "Low OCR Confidence",
  DUPLICATE_INVOICE: "Duplicate Invoice Detected",
};

/**
 * Human-readable label for a validation code with neutral fallback.
 */
export function getValidationCodeLabel(code: string): string {
  if (VALIDATION_CODE_LABELS[code]) {
    return VALIDATION_CODE_LABELS[code];
  }
  return code.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}

/**
 * Neutral fallback presentation for any unrecognized status string.
 */
function createNeutralPresentation(raw: string): StatusPresentation {
  const formatted = raw
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/^\w/, (c) => c.toUpperCase());
  return {
    label: formatted,
    icon: Tag,
    badgeClassName:
      "border-zinc-500/20 bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  };
}

export type StatusCategory =
  | "document"
  | "review"
  | "job"
  | "validation-severity"
  | "validation-status";

/**
 * Resolves a StatusPresentation for any given status string, category-directed
 * or globally searched, falling back to a clean neutral badge if unknown.
 */
export function getStatusPresentation(
  status: string | null | undefined,
  category?: StatusCategory,
): StatusPresentation {
  if (!status) {
    return createNeutralPresentation("Unknown");
  }

  if (category === "document" && status in DOCUMENT_STATUS_META) {
    return DOCUMENT_STATUS_META[status as DocumentStatus];
  }
  if (category === "review" && status in REVIEW_STATUS_META) {
    return REVIEW_STATUS_META[status as ReviewStatus];
  }
  if (category === "job" && status in JOB_STATUS_META) {
    return JOB_STATUS_META[status as JobStatus];
  }
  if (category === "validation-severity" && status in VALIDATION_SEVERITY_META) {
    return VALIDATION_SEVERITY_META[status as ValidationSeverity];
  }
  if (category === "validation-status" && status in VALIDATION_STATUS_META) {
    return VALIDATION_STATUS_META[status as ValidationStatus];
  }

  // Cross-category fallback search
  if (status in DOCUMENT_STATUS_META) return DOCUMENT_STATUS_META[status as DocumentStatus];
  if (status in REVIEW_STATUS_META) return REVIEW_STATUS_META[status as ReviewStatus];
  if (status in JOB_STATUS_META) return JOB_STATUS_META[status as JobStatus];
  if (status in VALIDATION_SEVERITY_META) return VALIDATION_SEVERITY_META[status as ValidationSeverity];
  if (status in VALIDATION_STATUS_META) return VALIDATION_STATUS_META[status as ValidationStatus];

  return createNeutralPresentation(status);
}

/**
 * Returns true if the document status is non-final (waiting or active).
 */
export function isNonFinalStatus(status: DocumentStatus): boolean {
  return status === "uploaded" || status === "processing";
}

/**
 * A processing job is terminal when succeeded or failed.
 */
export function isJobTerminal(status: JobStatus | string): boolean {
  return status === "succeeded" || status === "failed";
}

/**
 * Document detail is in a terminal state when:
 * 1. Document status itself is terminal (parsed or failed).
 * 2. Every job in processing_jobs is terminal (succeeded or failed).
 */
export function isDocumentTerminal(doc: DocumentDetailRead | null | undefined): boolean {
  if (!doc) return false;
  const isDocTerminal = doc.status === "parsed" || doc.status === "failed";
  if (!isDocTerminal) return false;

  const jobs = doc.processing_jobs || [];
  if (jobs.length === 0) return true;

  return jobs.every((job) => isJobTerminal(job.status));
}
