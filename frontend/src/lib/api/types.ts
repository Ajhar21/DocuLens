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

export interface DocumentItem {
  id: string;
  original_filename: string;
  content_type: string;
  file_ext: string;
  size_bytes: number;
  sha256: string;
  status: DocumentStatus;
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

