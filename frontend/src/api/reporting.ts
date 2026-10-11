import { apiRequest } from './client'

export interface KPICard {
  kpi_id: string
  kpi_name: string
  domain: string
  value: number | string
  formatted_value: string
  unit?: string
  comparison_value?: number | string
  change_pct?: number
  trend?: 'up' | 'down' | 'neutral'
}

export interface ExecutiveSummaryResponse {
  as_of_date: string
  period_start: string
  period_end: string
  scorecards: KPICard[]
}

export interface RevenueMarginMonthlyPoint {
  month: string
  gross_invoiced: number | string
  credit_notes: number | string
  net_revenue: number | string
  cogs: number | string
  gross_margin: number | string
  gross_margin_pct: number | string
  invoice_count: number
}

export interface RevenueReportResponse {
  period_start: string
  period_end: string
  net_revenue: number | string
  gross_margin: number | string
  gross_margin_pct: number | string
  total_invoices: number
  total_credit_notes: number
  trend: RevenueMarginMonthlyPoint[]
}

export interface ARAgingBucket {
  bucket: string
  label: string
  amount: number | string
  count: number
  percentage: number | string
}

export interface ARAgingCustomerRow {
  customer_id: number
  customer_no: string
  customer_name: string
  total_balance: number | string
  current: number | string
  days_1_30: number | string
  days_31_60: number | string
  days_61_90: number | string
  days_90_plus: number | string
}

export interface ARAgingResponse {
  as_of_date: string
  total_outstanding: number | string
  buckets: ARAgingBucket[]
  customers: ARAgingCustomerRow[]
  dso_days?: number | string
}

export interface PipelineStageSummary {
  stage: string
  label: string
  count: number
  nominal_amount: number | string
  weighted_amount: number | string
}

export interface PipelineReportResponse {
  as_of_date: string
  period_start: string
  period_end: string
  total_open_opportunities: number
  total_open_amount: number | string
  weighted_pipeline: number | string
  win_rate_pct: number | string
  lead_conversion_pct: number | string
  avg_sales_cycle_days: number | string
  stages: PipelineStageSummary[]
}

export interface LowStockItemRow {
  product_id: number
  sku: string
  name: string
  uom: string
  qty_on_hand: number | string
  qty_reserved: number | string
  qty_available: number | string
  reorder_point: number | string
  deficit: number | string
}

export interface WarehouseInventorySummary {
  warehouse_id: number
  warehouse_code: string
  warehouse_name: string
  total_value: number | string
  sku_count: number
}

export interface InventoryReportResponse {
  as_of_date: string
  total_inventory_value: number | string
  low_stock_count: number
  warehouses: WarehouseInventorySummary[]
  low_stock_items: LowStockItemRow[]
}

export interface SupplierSpendRow {
  supplier_id: number
  supplier_no: string
  supplier_name: string
  spend: number | string
  bill_count: number
  on_time_rate_pct?: number | string
}

export interface ProcurementReportResponse {
  period_start: string
  period_end: string
  total_purchase_spend: number | string
  overall_on_time_rate_pct: number | string
  suppliers: SupplierSpendRow[]
}

function buildQuery(params?: Record<string, string | undefined>): string {
  if (!params) return ''
  const searchParams = new URLSearchParams()
  for (const [key, val] of Object.entries(params)) {
    if (val !== undefined && val !== '') {
      searchParams.append(key, val)
    }
  }
  const str = searchParams.toString()
  return str ? `?${str}` : ''
}

export async function fetchExecutiveSummary(params?: {
  period_start?: string
  period_end?: string
  as_of_date?: string
}): Promise<ExecutiveSummaryResponse> {
  return apiRequest<ExecutiveSummaryResponse>(`/api/v1/reporting/summary${buildQuery(params)}`)
}

export async function fetchRevenueReport(params?: {
  period_start?: string
  period_end?: string
}): Promise<RevenueReportResponse> {
  return apiRequest<RevenueReportResponse>(`/api/v1/reporting/revenue${buildQuery(params)}`)
}

export async function fetchARAgingReport(params?: {
  as_of_date?: string
}): Promise<ARAgingResponse> {
  return apiRequest<ARAgingResponse>(`/api/v1/reporting/ar-aging${buildQuery(params)}`)
}

export async function fetchPipelineReport(params?: {
  period_start?: string
  period_end?: string
}): Promise<PipelineReportResponse> {
  return apiRequest<PipelineReportResponse>(`/api/v1/reporting/pipeline${buildQuery(params)}`)
}

export async function fetchInventoryReport(params?: {
  as_of_date?: string
}): Promise<InventoryReportResponse> {
  return apiRequest<InventoryReportResponse>(`/api/v1/reporting/inventory${buildQuery(params)}`)
}

export async function fetchProcurementReport(params?: {
  period_start?: string
  period_end?: string
}): Promise<ProcurementReportResponse> {
  return apiRequest<ProcurementReportResponse>(`/api/v1/reporting/procurement${buildQuery(params)}`)
}
