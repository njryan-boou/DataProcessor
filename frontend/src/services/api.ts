import type { AssistantPlan, AssistantStatus, ChartData, ChartKind, DatasetMetadata, Operation, Preview, Statistics } from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try { response = await fetch(`/api${path}`, init) } catch { throw new Error('Cannot reach DataFlow. Check that the backend is running and try again.') }
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.error?.message ?? payload?.detail ?? `Request failed (${response.status}). Please try again.`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
const json = (data: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
export async function uploadDataset(file: File) { const data = new FormData(); data.append('file', file); return request<DatasetMetadata>('/datasets/upload', { method: 'POST', body: data }) }
export const loadDemo = () => request<DatasetMetadata>('/datasets/demo', { method: 'POST' })
export const getMetadata = (id: string) => request<DatasetMetadata>(`/datasets/${id}`)
export const discardDataset = (id: string) => request<void>(`/datasets/${id}`, { method: 'DELETE' })
export const getPreview = (id: string, page = 1, pageSize = 50) => request<Preview>(`/datasets/${id}/preview?page=${page}&page_size=${pageSize}`)
export const getStatistics = (id: string) => request<Statistics>(`/datasets/${id}/statistics`)
export const transformDataset = (id: string, operation: Operation) => request<DatasetMetadata>(`/datasets/${id}/transform`, json(operation))
export const transformBatch = (id: string, operations: Operation[]) => request<DatasetMetadata>(`/datasets/${id}/transform-batch`, json({ operations }))
export const undoTransform = (id: string) => request<DatasetMetadata>(`/datasets/${id}/undo`, { method: 'POST' })
export const getAssistantStatus = () => request<AssistantStatus>('/assistant/status')
export const getConfig = () => request<{ max_upload_mb: number; max_rows: number; max_columns: number; history_limit: number }>('/config')
export const planOperations = (id: string, prompt: string) => request<AssistantPlan>(`/datasets/${id}/assistant/plan`, json({ prompt }))
export const getChart = (id: string, kind: ChartKind, x: string, y?: string) => request<ChartData>(`/datasets/${id}/chart?${new URLSearchParams({ kind, x, ...(y ? { y } : {}) })}`)
export async function downloadDataset(id: string): Promise<Blob> {
  const response = await fetch(`/api/datasets/${id}/export`)
  if (!response.ok) { const payload = await response.json().catch(() => null); throw new Error(payload?.error?.message ?? 'Export failed. Please try again.') }
  return response.blob()
}
