export type ColumnType = 'numeric' | 'text' | 'boolean' | 'datetime'
export type Scalar = string | number | boolean | null
export type Section = 'upload' | 'dataset' | 'clean' | 'transform' | 'visualize' | 'export'
export interface ColumnInfo { name: string; type: ColumnType; missing: number; unique: number }
export interface Operation { operation: string; parameters: Record<string, unknown> }
export interface HistoryEntry extends Operation { id: string; description: string; created_at: string }
export interface DatasetMetadata {
  id: string; filename: string; file_size: number; rows: number; column_count: number;
  missing_values: number; duplicate_rows: number; columns: ColumnInfo[]; version: number; history: HistoryEntry[]
}
export interface Preview { columns: string[]; rows: Record<string, Scalar>[]; total: number; page: number; page_size: number }
export interface ColumnStats extends ColumnInfo {
  count: number; mean?: number | null; median?: number | null; std?: number | null; min?: number | string | null;
  max?: number | string | null; q1?: number | null; q3?: number | null; outlier_count?: number;
  top_values?: { value: Scalar; count: number }[]
}
export interface Statistics { columns: ColumnStats[]; warnings: { code: string; message: string; column?: string }[]; duplicate_rows: number }
export type ChartKind = 'histogram' | 'bar' | 'line' | 'scatter' | 'box'
export interface ChartData { kind: ChartKind; x: string; y?: string | null; points: Record<string, unknown>[]; [key: string]: unknown }
export interface AssistantPlan { operations: Operation[]; provider: string; explanation: string }
export interface AssistantStatus { provider: string; available: boolean; [key: string]: unknown }
