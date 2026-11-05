import { apiRequest } from "@/lib/api/client";
import type {
  ExcelSheetsResponse,
  ReconcilePdfExcelRequest,
  ReconcilePdfPdfRequest,
  ReconciliationJobDetail,
  ReconciliationJobPage,
} from "@/lib/api/types";

export interface ListReconciliationsParams {
  page?: number;
  page_size?: number;
  document_id?: string;
}

export async function fetchReconciliations(
  params: ListReconciliationsParams = {},
): Promise<ReconciliationJobPage> {
  return apiRequest<ReconciliationJobPage>("/reconciliations", {
    method: "GET",
    query: {
      page: params.page ?? 1,
      page_size: params.page_size ?? 20,
      document_id: params.document_id || undefined,
    },
  });
}

export async function fetchReconciliationDetail(
  id: string,
): Promise<ReconciliationJobDetail> {
  return apiRequest<ReconciliationJobDetail>(`/reconciliations/${id}`, {
    method: "GET",
  });
}

export async function reconcilePdfPdf(
  payload: ReconcilePdfPdfRequest,
): Promise<ReconciliationJobDetail> {
  return apiRequest<ReconciliationJobDetail>("/reconciliations/pdf-pdf", {
    method: "POST",
    json: payload,
  });
}

export async function reconcilePdfExcel(
  payload: ReconcilePdfExcelRequest,
): Promise<ReconciliationJobDetail> {
  return apiRequest<ReconciliationJobDetail>("/reconciliations/pdf-excel", {
    method: "POST",
    json: payload,
  });
}

export async function fetchExcelSheets(
  documentId: string,
): Promise<ExcelSheetsResponse> {
  return apiRequest<ExcelSheetsResponse>(
    `/reconciliations/excel/${documentId}/sheets`,
    {
      method: "GET",
    },
  );
}

