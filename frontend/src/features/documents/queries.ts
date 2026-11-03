import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError } from "@/lib/api/errors";
import type { ListDocumentsParams } from "@/lib/api/types";
import {
  fetchDocuments,
  fetchUploadPolicy,
  uploadDocumentsBatch,
} from "./api";
import { FALLBACK_UPLOAD_POLICY } from "./file-precheck";
import { isNonFinalStatus } from "./status";

export const DOCUMENTS_QUERY_KEY = ["documents"] as const;
export const UPLOAD_POLICY_QUERY_KEY = ["documents", "upload-policy"] as const;

export const POLL_INTERVAL_MS = 2_500;

export function useUploadPolicy() {
  return useQuery({
    queryKey: UPLOAD_POLICY_QUERY_KEY,
    queryFn: fetchUploadPolicy,
    staleTime: 30 * 60 * 1000,
    placeholderData: FALLBACK_UPLOAD_POLICY,
  });
}

export function useDocumentsQuery(params: ListDocumentsParams) {
  return useQuery({
    queryKey: [...DOCUMENTS_QUERY_KEY, params] as const,
    queryFn: () => fetchDocuments(params),
    placeholderData: keepPreviousData,
    // Auto-refetch every 2.5s ONLY while any document in the current page is in a
    // non-final status (`uploaded` or `processing`). Stops automatically once all
    // documents reach `parsed` or `failed`.
    refetchInterval: (query) => {
      const items = query.state.data?.items;
      if (!items || items.length === 0) return false;
      const hasActiveWork = items.some((doc) => isNonFinalStatus(doc.status));
      return hasActiveWork ? POLL_INTERVAL_MS : false;
    },
  });
}

export function useUploadDocumentsMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: uploadDocumentsBatch,
    onSuccess: (batch) => {
      void queryClient.invalidateQueries({ queryKey: DOCUMENTS_QUERY_KEY });

      if (batch.accepted_count > 0 && batch.rejected_count === 0) {
        toast.success(
          `${batch.accepted_count} ${batch.accepted_count === 1 ? "document" : "documents"} uploaded and queued.`,
        );
      } else if (batch.accepted_count > 0 && batch.rejected_count > 0) {
        toast.warning(
          `${batch.accepted_count} accepted, ${batch.rejected_count} rejected. Review the per-file details.`,
        );
      } else {
        toast.error(
          `All ${batch.rejected_count} ${batch.rejected_count === 1 ? "file was" : "files were"} rejected. See details below.`,
        );
      }
    },
    onError: (err) => {
      if (err instanceof DOMException && err.name === "AbortError") {
        toast.info("Upload cancelled.");
        return;
      }
      if (err instanceof ApiError) {
        if (err.kind === "forbidden") {
          toast.error("You do not have permission to upload documents.");
          return;
        }
        toast.error(err.message);
        return;
      }
      toast.error("Upload failed. Please try again.");
    },
  });
}

