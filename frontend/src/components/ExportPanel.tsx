import { Check, Download, FileSpreadsheet, LoaderCircle, ShieldCheck } from 'lucide-react'
import type { DatasetMetadata } from '../types'

export default function ExportPanel({ metadata, busy, onDownload }: { metadata: DatasetMetadata; busy: boolean; onDownload: () => Promise<void> }) {
  const filename = metadata.filename.replace(/\.csv$/i,'') + '_processed.csv'
  const changes = metadata.history.filter(entry => entry.operation !== 'upload').length
  return <section className="card export-card"><div className="export-illustration"><FileSpreadsheet size={42} strokeWidth={1.25} /><span><Check size={17} /></span></div><span className="eyebrow">FROM HERE TO ANYWHERE</span><h2>Your data, ready to go.</h2><p>Download your current working dataset as a CSV.<br />All your applied transformations are included.</p><div className="export-file"><FileSpreadsheet size={20} /><div><strong>{filename}</strong><span>{metadata.rows.toLocaleString()} rows · {metadata.column_count} columns · {changes} {changes === 1 ? 'transformation' : 'transformations'}</span></div><span className="format-tag">CSV</span></div><button className="button button-primary" disabled={busy} onClick={() => void onDownload()}>{busy ? <LoaderCircle size={16} className="spin" /> : <Download size={16} />}{busy ? 'Preparing download…' : 'Download processed CSV'}</button><div className="export-note"><ShieldCheck size={13} /> Your original uploaded dataset is preserved.</div></section>
}
