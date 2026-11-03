import { apiRequest, uploadWithProgress } from "@/lib/api/client";
import type {
  BatchUploadResponse,
  DocumentPage,
  ListDocumentsParams,
  UploadPolicy,
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

