import { ChevronLeft, ChevronRight, Hash, Type, CalendarDays, ToggleLeft, LoaderCircle, Table2 } from 'lucide-react'
import type { DatasetMetadata, Preview, Scalar } from '../types'

export function displayValue(value: Scalar | undefined) { if (value === null || value === undefined) return '—'; if (typeof value === 'boolean') return value ? 'true' : 'false'; return String(value) }
interface Props { metadata: DatasetMetadata; preview: Preview | null; loading: boolean; page: number; onPage: (page: number) => void }
export default function DatasetTable({ metadata, preview, loading, page, onPage }: Props) {
  const pageSize = preview?.page_size ?? 50
  const pages = Math.max(1, Math.ceil(metadata.rows / pageSize))
  return <section className="card dataset-card" aria-label="Dataset preview">
    <div className="card-header"><div><div className="card-title"><Table2 size={18} /><h2>Data preview</h2><span className="badge">{metadata.rows.toLocaleString()} rows</span></div><p>Your working dataset. Every change is reflected here.</p></div><span className="preview-caption">{pageSize} rows per page</span></div>
    <div className={`table-scroll ${loading ? 'is-loading' : ''}`} aria-busy={loading}>
      {loading && <div className="table-loading"><LoaderCircle size={24} className="spin" /><span>Loading rows…</span></div>}
      <table className="dataset-table"><thead><tr><th className="row-number">#</th>{metadata.columns.map(column => { const Icon = column.type === 'numeric' ? Hash : column.type === 'datetime' ? CalendarDays : column.type === 'boolean' ? ToggleLeft : Type; return <th key={column.name}><span className="column-name">{column.name}</span><span className="column-type"><Icon size={12} /> {column.type}</span></th> })}</tr></thead><tbody>{preview?.rows.map((row, index) => <tr key={`${page}-${index}`}><td className="row-number">{(page - 1) * pageSize + index + 1}</td>{metadata.columns.map(column => <td key={column.name} className={`${column.type === 'numeric' ? 'numeric-cell' : ''} ${row[column.name] == null ? 'missing-cell' : ''}`} title={displayValue(row[column.name])}>{displayValue(row[column.name])}</td>)}</tr>)}</tbody></table>
      {!loading && preview?.rows.length === 0 && <div className="table-empty">No rows match your current transformations. Undo your last change to bring them back.</div>}
    </div>
    <div className="table-footer"><span>{metadata.rows === 0 ? '0 rows' : `Showing ${((page - 1) * pageSize + 1).toLocaleString()}–${Math.min(page * pageSize, metadata.rows).toLocaleString()} of ${metadata.rows.toLocaleString()} rows`}<span className="missing-key"><i /> missing value</span></span><div className="pagination"><button className="icon-button" aria-label="Previous page" disabled={page <= 1 || loading} onClick={() => onPage(page - 1)}><ChevronLeft size={16} /></button><span>Page {page} of {pages}</span><button className="icon-button" aria-label="Next page" disabled={page >= pages || loading} onClick={() => onPage(page + 1)}><ChevronRight size={16} /></button></div></div>
  </section>
}
