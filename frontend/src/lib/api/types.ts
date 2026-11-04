export type UserRole = "admin" | "reviewer" | "viewer";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface UserSummary {
  id: string;
  full_name: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
}

export type DocumentStatus = "uploaded" | "processing" | "parsed" | "failed";

export type ReviewStatus =
  | "pending"
  | "needs_review"
  | "approved"
  | "rejected"
  | "not_required";

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

export interface FileUploadItemResult {
  filename: string;
  status: "accepted" | "rejected";
  document_id: string | null;
  job_id: string | null;
  reason: string | null;
}

export interface BatchUploadResponse {
  results: FileUploadItemResult[];
  accepted_count: number;
  rejected_count: number;
}

export interface UploadPolicy {
  max_upload_mb: number;
  max_upload_bytes: number;
  allowed_extensions: string[];
  accepted_content_types: string[];
}

export interface ErrorDetail {
  field: string | null;
  message: string;
  type: string | null;
}

export interface ErrorInfo {
  code: string;
  details: ErrorDetail[];
}

export interface APIResponse<T> {
  success: boolean;
  message: string;
  data: T | null;
  error: ErrorInfo | null;
}

// ---------------------------------------------------------------------------
// Day 2 Detail Schemas (mirroring backend/app/schemas/document.py & job.py)
// ---------------------------------------------------------------------------

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

export interface InvoiceLineItemRead {
  id: string;
  line_no: number;
  description: string | null;
  quantity: string | number | null;
  unit_price: string | number | null;
  amount: string | number | null;
}

export interface ExtractedInvoiceRead {
  id: string;
  document_id: string;
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  customer_name: string | null;
  subtotal: string | number | null;
  tax: string | number | null;
  total: string | number | null;
  discount?: string | number | null;
  shipping?: string | number | null;
  currency: string | null;
  extraction_metadata: Record<string, unknown>;
  line_items: InvoiceLineItemRead[];
  created_at: string;
  updated_at: string;
}

export interface ValidationResultRead {
  id: string;
  document_id: string;
  validation_code: string;
  field_name: string | null;
  severity: ValidationSeverity | string;
  message: string;
  expected_value: string | null;
  actual_value: string | null;
  status: ValidationStatus | string;
  created_at: string;
}

export interface DocumentDetailRead extends DocumentItem {
  review_status: ReviewStatus | null;
  latest_job: JobRead | null;
  processing_jobs: JobRead[];
  parse_summary: ParseSummary | null;
  extracted_invoice: ExtractedInvoiceRead | null;
  validation_results: ValidationResultRead[];
}
