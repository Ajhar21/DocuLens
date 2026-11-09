import { apiRequest } from "@/lib/api/client";
import type { SearchResponse } from "@/lib/api/types";

export type SearchMode = "keyword" | "semantic" | "hybrid";

export interface SearchParams {
  q?: string;
  mode?: SearchMode;
  supplier_name?: string;
  date_from?: string;
  date_to?: string;
  amount_min?: string | number;
  amount_max?: string | number;
  review_status?: string;
  limit?: number;
  offset?: number;
}

export async function searchDocuments(
  params: SearchParams,
): Promise<SearchResponse> {
  const cleanedQ = params.q?.trim();
  return apiRequest<SearchResponse>("/search", {
    method: "GET",
    query: {
      q: cleanedQ || undefined,
      mode: params.mode || "hybrid",
      supplier_name: params.supplier_name || undefined,
      date_from: params.date_from || undefined,
      date_to: params.date_to || undefined,
      amount_min: params.amount_min != null && params.amount_min !== "" ? params.amount_min : undefined,
      amount_max: params.amount_max != null && params.amount_max !== "" ? params.amount_max : undefined,
      review_status: params.review_status || undefined,
      limit: params.limit ?? 20,
      offset: params.offset ?? 0,
    },
  });
}

