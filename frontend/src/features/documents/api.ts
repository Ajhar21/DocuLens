import { apiRequest, uploadWithProgress } from "@/lib/api/client";
import type {
  BatchUploadResponse,
  DocumentPage,
  ListDocumentsParams,
  UploadPolicy,
  DocumentDetailRead,
  JobRead,
} from "@/lib/api/types";

export async function fetchDocuments(
  params: ListDocumentsParams,
): Promise<DocumentPage> {
  return apiRequest<DocumentPage>("/documents", {
    method: "GET",
    query: {
      limit: params.limit,
      offset: params.offset,
      status: params.status,
      review_status: params.review_status,
    },
  });
}

export async function fetchUploadPolicy(): Promise<UploadPolicy> {
  return apiRequest<UploadPolicy>("/documents/upload-policy", {
    method: "GET",
  });
}

export async function uploadDocumentsBatch(options: {
  files: File[];
  onProgress?: (percent: number) => void;
  signal?: AbortSignal;
}): Promise<BatchUploadResponse> {
  const formData = new FormData();
  for (const file of options.files) {
    formData.append("files", file, file.name);
  }
  return uploadWithProgress<BatchUploadResponse>("/documents", {
    formData,
    onProgress: options.onProgress,
    signal: options.signal,
  });
}

/** Fetch a single document detail, including processing jobs, extraction and validation */
export async function fetchDocumentDetail(id: string): Promise<DocumentDetailRead> {
  return apiRequest<DocumentDetailRead>(`/documents/${id}`, { method: "GET" });
}

/** Re‑run a pipeline stage for a document */
export async function reprocessDocument(
  id: string,
  stage: "extraction" | "embedding",
): Promise<JobRead> {
  return apiRequest<JobRead>(`/documents/${id}/reprocess?stage=${stage}`, {
    method: "POST",
  });
}

