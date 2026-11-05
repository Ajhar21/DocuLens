import { apiDownloadBlob, apiRequest } from "@/lib/api/client";
import type {
  CorrectionItem,
  ReviewDetailRead,
  ReviewQueuePage,
} from "@/lib/api/types";

export interface ListReviewsParams {
  limit?: number;
  offset?: number;
  review_status?: string;
}

export async function fetchReviewQueue(
  params: ListReviewsParams = {},
): Promise<ReviewQueuePage> {
  return apiRequest<ReviewQueuePage>("/reviews", {
    method: "GET",
    query: {
      limit: params.limit,
      offset: params.offset,
      review_status: params.review_status,
    },
  });
}

export async function fetchReviewDetail(
  documentId: string,
): Promise<ReviewDetailRead> {
  return apiRequest<ReviewDetailRead>(`/reviews/${documentId}`, {
    method: "GET",
  });
}

export async function submitCorrections(
  documentId: string,
  corrections: CorrectionItem[],
): Promise<ReviewDetailRead> {
  return apiRequest<ReviewDetailRead>(`/reviews/${documentId}/corrections`, {
    method: "PATCH",
    json: corrections,
  });
}

export async function approveDocument(
  documentId: string,
  notes?: string,
): Promise<ReviewDetailRead> {
  return apiRequest<ReviewDetailRead>(`/reviews/${documentId}/approve`, {
    method: "POST",
    json: notes ? { notes } : {},
  });
}

export async function rejectDocument(
  documentId: string,
  reason: string,
): Promise<ReviewDetailRead> {
  return apiRequest<ReviewDetailRead>(`/reviews/${documentId}/reject`, {
    method: "POST",
    json: { reason },
  });
}

export async function fetchDocumentFileBlob(documentId: string): Promise<Blob> {
  return apiDownloadBlob(`/documents/${documentId}/file`);
}

