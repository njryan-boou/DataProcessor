import { Check, Clock3, FileSpreadsheet, History, LoaderCircle, Undo2 } from 'lucide-react'
import type { DatasetMetadata } from '../types'

export default function HistoryPanel({ metadata, busy, onUndo }: { metadata: DatasetMetadata; busy: boolean; onUndo: () => Promise<void> }) {
  const operations = metadata.history.filter(entry => entry.operation !== 'upload')
  return <section className="card history-card"><div className="card-header"><div className="card-title"><History size={17} /><h2>Operation history</h2><span className="badge">{operations.length}</span></div><button className="text-button" disabled={!operations.length || busy} onClick={() => void onUndo()}>{busy ? <LoaderCircle size={14} className="spin" /> : <Undo2 size={14} />} Undo last</button></div>
    <ol className="history-list"><li className="history-entry original"><div className="history-dot"><FileSpreadsheet size={12} /></div><div><strong>Original dataset uploaded</strong><span>{metadata.filename}</span></div><span className="history-status">Preserved</span></li>{operations.map((entry, index) => <li className="history-entry" key={entry.id}><div className="history-dot"><Check size={12} /></div><div><strong>{entry.description}</strong><span>Step {index + 1}<span className="dot-separator"> · </span>{new Date(entry.created_at).toLocaleTimeString(undefined, {hour:'2-digit',minute:'2-digit'})}</span></div><Clock3 size={12} /></li>)}</ol>
    {!operations.length && <p className="history-empty">Your data’s journey starts here. Applied transformations will appear in this history.</p>}
    <div className="history-note">Each step can be undone, one at a time.</div>
  </section>
}
