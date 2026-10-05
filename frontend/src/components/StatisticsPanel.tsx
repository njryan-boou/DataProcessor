import { AlertTriangle, ArrowUpRight, BarChart3, ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'
import type { Statistics } from '../types'

const number = (value: unknown) => typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 3 }) : value == null ? '—' : String(value)
export default function StatisticsPanel({ statistics }: { statistics: Statistics | null }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  if (!statistics) return null
  return <>
    {statistics.warnings.length > 0 && <section className="insight-banner"><div className="insight-icon"><AlertTriangle size={18} /></div><div><h3>A few things worth a closer look</h3><p>{statistics.warnings.length} {statistics.warnings.length === 1 ? 'recommendation' : 'recommendations'} found. Your data stays unchanged until you choose a transformation.</p><div className="warning-list">{statistics.warnings.map((warning, index) => <span key={index}>{warning.message}</span>)}</div></div></section>}
    <section className="card statistics-card"><div className="card-header"><div><div className="card-title"><BarChart3 size={18} /><h2>Column insights</h2><span className="badge">{statistics.columns.length} columns</span></div><p>A closer look at what makes up your dataset.</p></div><span className="preview-caption">Click a column to explore <ArrowUpRight size={14} /></span></div>
      <div className="statistics-columns">{statistics.columns.map(column => <div className={`stat-column ${expanded === column.name ? 'expanded' : ''}`} key={column.name}><button className="stat-column-heading" onClick={() => setExpanded(expanded === column.name ? null : column.name)}><span><strong>{column.name}</strong><span className={`type-badge ${column.type}`}>{column.type}</span></span><span className="stat-column-glance"><span>{column.unique.toLocaleString()} unique</span><span className={column.missing > 0 ? 'text-amber' : ''}>{column.missing} missing</span>{expanded === column.name ? <ChevronUp size={16} /> : <ChevronDown size={16} />}</span></button>
        {expanded === column.name && <div className="stat-column-details">{column.type === 'numeric' ? <div className="stat-details-grid">{[['Count', column.count],['Mean',column.mean],['Median',column.median],['Std. deviation',column.std],['Minimum',column.min],['Maximum',column.max],['25th percentile',column.q1],['75th percentile',column.q3],['Outliers (IQR)',column.outlier_count ?? 0]].map(([label,value]) => <div key={String(label)}><span>{label}</span><strong>{number(value)}</strong></div>)}</div> : <div className="frequency-list"><span className="eyebrow">MOST COMMON VALUES</span>{column.top_values?.map((entry, index) => <div className="frequency-row" key={index}><span>{number(entry.value)}</span><div className="frequency-track"><div style={{ width: `${Math.min(100, entry.count / Math.max(1, column.count) * 100)}%` }} /></div><strong>{entry.count.toLocaleString()}</strong></div>)}{!column.top_values?.length && <p>No non-missing values in this column.</p>}</div>}</div>}
      </div>)}</div>
    </section>
  </>
}
