import { apiRequest } from './client'

export interface ImportBatch {
  id: number
  entity_type: 'customer' | 'product' | 'contact'
  file_name: string
  file_sha256: string
  source_label?: string | null
  status: 'uploaded' | 'validated' | 'committed' | 'failed' | 'cancelled'
  row_count: number
  valid_count: number
  error_count: number
  committed_count: number
  uploaded_by?: number | null
  created_at: string
  committed_at?: string | null
}

export interface StagingRow {
  id: number
  row_number: number
  name?: string | null
  email?: string | null
  phone?: string | null
  tin?: string | null
  city?: string | null
  province?: string | null
  customer_type?: string | null
  payment_terms?: string | null
  credit_limit?: string | null
  sku?: string | null
  product_type?: string | null
  uom?: string | null
  list_price?: string | null
  reorder_point?: string | null
  customer_id?: string | null
  first_name?: string | null
  last_name?: string | null
  job_title?: string | null
  validation_errors?: Array<{ field: string; message: string }> | null
  committed_id?: number | null
  raw: Record<string, unknown>
}

export interface ImportBatchDetailResponse {
  batch: ImportBatch
  staging_rows: StagingRow[]
  total_staging_rows: number
}

export interface CommitResultResponse {
  batch_id: number
  status: string
  committed_count: number
  error_count: number
  message: string
}

export async function uploadImportCsv(
  file: File,
  entityType: 'customer' | 'product' | 'contact',
  sourceLabel?: string
): Promise<ImportBatch> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('entity_type', entityType)
  if (sourceLabel) {
    formData.append('source_label', sourceLabel)
  }

  return apiRequest<ImportBatch>('/api/v1/imports/upload', {
    method: 'POST',
    body: formData,
  })
}

export async function uploadRawCsv(payload: {
  entity_type: string
  file_name: string
  csv_content: string
  source_label?: string
}): Promise<ImportBatch> {
  return apiRequest<ImportBatch>('/api/v1/imports/upload-raw', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function listImportBatches(
  entityType?: string,
  status?: string,
  limit = 50,
  offset = 0
): Promise<ImportBatch[]> {
  const params = new URLSearchParams()
  if (entityType) params.set('entity_type', entityType)
  if (status) params.set('status', status)
  params.set('limit', String(limit))
  params.set('offset', String(offset))

  return apiRequest<ImportBatch[]>(`/api/v1/imports/batches?${params.toString()}`)
}

export async function getImportBatchDetail(
  batchId: number,
  limit = 100,
  offset = 0
): Promise<ImportBatchDetailResponse> {
  return apiRequest<ImportBatchDetailResponse>(
    `/api/v1/imports/batches/${batchId}?limit=${limit}&offset=${offset}`
  )
}

export async function validateImportBatch(batchId: number): Promise<ImportBatch> {
  return apiRequest<ImportBatch>(`/api/v1/imports/batches/${batchId}/validate`, {
    method: 'POST',
  })
}

export async function commitImportBatch(batchId: number): Promise<CommitResultResponse> {
  return apiRequest<CommitResultResponse>(`/api/v1/imports/batches/${batchId}/commit`, {
    method: 'POST',
  })
}
