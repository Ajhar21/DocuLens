import {
  CheckCircle2,
  Clock,
  Loader2,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type { DocumentStatus } from "@/lib/api/types";

export interface StatusPresentation {
  label: string;
  description: string;
  icon: LucideIcon;
  spin?: boolean;
  badgeClassName: string;
}

/**
 * Uses the real backend DocumentStatus vocabulary (`uploaded`, `processing`,
 * `parsed`, `failed`) with distinct color + icon + text (never color alone).
 */
export const DOCUMENT_STATUS_META: Record<DocumentStatus, StatusPresentation> = {
  uploaded: {
    label: "Uploaded",
    description: "Queued and waiting for a background worker",
    icon: Clock,
    badgeClassName:
      "border-status-uploaded/25 bg-status-uploaded-bg text-status-uploaded",
  },
  processing: {
    label: "Processing",
    description: "Worker is actively extracting pages and tables",
    icon: Loader2,
    spin: true,
    badgeClassName:
      "border-status-processing/25 bg-status-processing-bg text-status-processing",
  },
  parsed: {
    label: "Parsed",
    description: "Document extraction completed",
    icon: CheckCircle2,
    badgeClassName:
      "border-status-parsed/25 bg-status-parsed-bg text-status-parsed",
  },
  failed: {
    label: "Failed",
    description: "Extraction failed after maximum retry attempts",
    icon: XCircle,
    badgeClassName:
      "border-status-failed/25 bg-status-failed-bg text-status-failed",
  },
};

export function isNonFinalStatus(status: DocumentStatus): boolean {
  return status === "uploaded" || status === "processing";
}

