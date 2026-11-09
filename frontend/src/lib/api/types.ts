import type { components } from "./schema";

export type Schemas = components["schemas"];

// ---------------------------------------------------------------------------
// Canonical Role & Auth Types (from OpenAPI schema)
// ---------------------------------------------------------------------------

export type RoleName = Schemas["RoleName"];

/** Legacy alias union for backwards compatibility while canonicalizing on RoleName */
export type UserRole = RoleName | "admin" | "reviewer" | "viewer";

export type UserRead = Schemas["UserRead"];

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: RoleName;
  is_active: boolean;
  status?: string;
  must_change_password?: boolean;
  token_version?: number;
  last_login_at?: string | null;
  invited_by?: string | null;
  deactivated_at?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export type UserSummary = Schemas["UserSummary"];

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
}

// ---------------------------------------------------------------------------
// Document & Job Types (Day 1 - Day 2)
// ---------------------------------------------------------------------------

export type DocumentStatus = "uploaded" | "processing" | "parsed" | "failed";

export type ReviewStatus = Schemas["ReviewStatus"];

export type JobType = "parse" | "extraction" | "embedding";

export type JobStatus = "pending" | "running" | "succeeded" | "failed";

export type ValidationSeverity = "ERROR" | "WARNING" | "INFO";

export type ValidationStatus = "PASSED" | "FAILED" | "SKIPPED";

export interface DocumentItem {
  id: string;
  original_filename: string;
  content_type: string;
  file_ext: string;
  size_bytes: number;
  sha256: string;
  status: DocumentStatus;
  review_status: ReviewStatus | null;
  error: string | null;
  uploaded_by: string;
  uploader: UserSummary;
  created_at: string;
  updated_at: string;
}

export interface DocumentPage {
  items: DocumentItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ListDocumentsParams {
  limit?: number;
  offset?: number;
  status?: DocumentStatus;
  review_status?: ReviewStatus;
}

export type FileUploadItemResult = Schemas["FileUploadItemResult"];
export type BatchUploadResponse = Schemas["BatchUploadResponse"];
export type UploadPolicy = Schemas["UploadPolicy"];

export type ErrorDetail = Schemas["ErrorDetail"];
export type ErrorInfo = Schemas["ErrorInfo"];

export interface APIResponse<T> {
  success: boolean;
  message: string;
  data: T | null;
  error: ErrorInfo | null;
}

export interface JobRead {
  id: string;
  document_id: string;
  job_type: JobType | string;
  status: JobStatus;
  current_stage: string | null;
  attempts: number;
  attempt_count: number;
  max_attempts: number;
  run_after: string;
  locked_by: string | null;
  locked_at: string | null;
  last_error: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  completed_at: string | null;
}

export interface ParseSummary {
  page_count: number;
  table_count: number;
  ocr_used: boolean;
  metadata: Record<string, unknown>;
  pages: Record<string, unknown>[];
  tables: Record<string, unknown>[];
  created_at: string;
}

export type InvoiceLineItemRead = Schemas["InvoiceLineItemRead"];
export type ExtractedInvoiceRead = Schemas["ExtractedInvoiceRead"] & {
  discount?: string | number | null;
  shipping?: string | number | null;
};
export type ValidationResultRead = Schemas["ValidationResultRead"];

export interface DocumentDetailRead extends DocumentItem {
  review_status: ReviewStatus | null;
  latest_job: JobRead | null;
  processing_jobs: JobRead[];
  parse_summary: ParseSummary | null;
  extracted_invoice: ExtractedInvoiceRead | null;
  validation_results: ValidationResultRead[];
}

// ---------------------------------------------------------------------------
// Day 3 Schemas: Review, Reconciliation, Search (re-exported from OpenAPI)
// ---------------------------------------------------------------------------

export type ReviewQueueItem = Schemas["ReviewQueueItem"];
export type ReviewQueuePage = Schemas["ReviewQueuePage"];
export type ReviewDetailRead = Schemas["ReviewDetailRead"];
export interface CorrectionItem {
  field_name: string;
  corrected_value?: unknown;
  reason?: string | null;
}
export type DocumentCorrectionRead = Schemas["DocumentCorrectionRead"];
export type ApprovePayload = Schemas["ApprovePayload"];
export type RejectPayload = Schemas["RejectPayload"];

export type ReconcilePdfPdfRequest = Schemas["ReconcilePdfPdfRequest"];
export type ReconcilePdfExcelRequest = Schemas["ReconcilePdfExcelRequest"];
export type ReconciliationJobSummary = Schemas["ReconciliationJobSummary"];
export type ReconciliationJobDetail = Schemas["ReconciliationJobDetail"];
export type ReconciliationJobPage = Schemas["ReconciliationJobPage"];
export type ReconciliationJobPagination = Schemas["ReconciliationJobPagination"];
export type ReconciliationResultRead = Schemas["ReconciliationResultRead"];
export type ExcelSheetsResponse = Schemas["ExcelSheetsResponse"];

export type SearchResponse = Schemas["SearchResponse"];
export type SearchHit = Schemas["SearchHit"];
export type SearchDocumentSummary = Schemas["SearchDocumentSummary"];
export type SearchInvoiceSummary = Schemas["SearchInvoiceSummary"];

// ---------------------------------------------------------------------------
// Day 4 Schemas: User Lifecycle, Invites, Password Change & Audit Logs
// ---------------------------------------------------------------------------

export type UserInviteRequest = Schemas["UserInviteRequest"];
export type UserInviteResponse = Schemas["UserInviteResponse"];
export type PasswordResetLinkResponse = Schemas["PasswordResetLinkResponse"];
export type ChangePasswordRequest = Schemas["ChangePasswordRequest"];
export type AcceptInviteRequest = Schemas["AcceptInviteRequest"];
export type ResetPasswordRequest = Schemas["ResetPasswordRequest"];
export type AuditLogPage = Schemas["AuditLogPage"];
export type AuditLogRead = AuditLogPage["items"][number];
