import { lazy, Suspense, useEffect, useState } from 'react'
import { ArrowLeftRight, ArrowUpRight, ChartNoAxesCombined, Check, ChevronRight, Database, Download, FileSpreadsheet, Layers3, Leaf, LoaderCircle, Menu, Table2, Undo2, Upload, WandSparkles, X } from 'lucide-react'
import UploadZone from './components/UploadZone'
import DatasetTable from './components/DatasetTable'
import StatisticsPanel from './components/StatisticsPanel'
import OperationForm from './components/OperationForm'
import HistoryPanel from './components/HistoryPanel'
import AssistantPanel from './components/AssistantPanel'
import ExportPanel from './components/ExportPanel'
import * as api from './services/api'
import type { DatasetMetadata, Operation, Preview, Section, Statistics } from './types'

const ChartPanel = lazy(() => import('./components/ChartPanel'))

const navigation: { key: Section; label: string; icon: typeof Upload }[] = [{ key:'upload',label:'Upload',icon:Upload },{ key:'dataset',label:'Dataset',icon:Table2 },{ key:'clean',label:'Clean',icon:WandSparkles },{ key:'transform',label:'Transform',icon:ArrowLeftRight },{ key:'visualize',label:'Visualize',icon:ChartNoAxesCombined },{ key:'export',label:'Export',icon:Download }]
const sectionCopy: Record<Section, { title: string; text: string }> = { upload:{title:'Your next insight starts here.',text:'Bring your data into one clear, connected workspace.'}, dataset:{title:'A clearer view of your data.',text:'Explore your dataset, spot patterns, and see what needs attention.'}, clean:{title:'A little cleanup goes a long way.',text:'Resolve missing values and duplicates. Keep every change reversible.'}, transform:{title:'Shape your data for what’s next.',text:'Filter, sort, and refine your columns with a few simple steps.'}, visualize:{title:'Let your data tell the story.',text:'Turn columns into clear charts and discover the patterns within.'}, export:{title:'Ready for its next chapter.',text:'Take your processed dataset with you as a fresh CSV file.'} }
const size = (bytes: number) => bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${(bytes / 1024).toFixed(1)} KB`

export default function App() {
  const [section, setSection] = useState<Section>('upload')
  const [metadata, setMetadata] = useState<DatasetMetadata | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [statistics, setStatistics] = useState<Statistics | null>(null)
  const [page, setPage] = useState(1)
  const [busy, setBusy] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [error, setError] = useState('')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [uploadLimit, setUploadLimit] = useState(20)
  const [notice, setNotice] = useState('')
  useEffect(() => { api.getConfig().then(config => setUploadLimit(config.max_upload_mb)).catch(() => {}) }, [])

  useEffect(() => {
    if (!metadata) return
    let cancelled = false
    setPreviewLoading(true)
    api.getPreview(metadata.id, page).then(data => { if (!cancelled) setPreview(data) }).catch(cause => { if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not load preview.') }).finally(() => { if (!cancelled) setPreviewLoading(false) })
    return () => { cancelled = true }
  }, [metadata?.id, metadata?.version, page])
  useEffect(() => {
    if (!metadata) return
    let cancelled = false
    api.getStatistics(metadata.id).then(data => { if (!cancelled) setStatistics(data) }).catch(cause => { if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not load statistics.') })
    return () => { cancelled = true }
  }, [metadata?.id, metadata?.version])
  const load = async (task: () => Promise<DatasetMetadata>) => {
    setBusy(true); setError(''); setNotice('')
    try { const data = await task(); const previous = metadata?.id; setMetadata(data); setPage(1); setPreview(null); setStatistics(null); setSection('dataset'); if (previous && previous !== data.id) void api.discardDataset(previous).catch(() => {}) } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load this dataset.') } finally { setBusy(false) }
  }
  const update = async (task: () => Promise<DatasetMetadata>, message: string) => {
    setBusy(true); setError(''); setNotice('')
    try { const data = await task(); setMetadata(data); setPage(1); setPreview(null); setStatistics(null); setNotice(message); return true } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not apply this operation.'); return false } finally { setBusy(false) }
  }
  const apply = async (operation: Operation) => { if (metadata) await update(() => api.transformDataset(metadata.id, operation), operation.operation === 'detect_outliers' ? 'Outlier detection recorded. Review potential outliers in Column insights below.' : 'Operation applied. Your dataset and insights are up to date.') }
  const applyBatch = async (operations: Operation[]) => metadata ? update(() => api.transformBatch(metadata.id, operations), `${operations.length} operations applied. Your plan is now part of the dataset history.`) : false
  const undo = async () => { if (metadata) await update(() => api.undoTransform(metadata.id), 'Last operation undone. Your previous dataset has been restored.') }
  const download = async () => {
    if (!metadata) return
    setBusy(true); setError('')
    try { const blob = await api.downloadDataset(metadata.id); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = metadata.filename.replace(/\.csv$/i,'') + '_processed.csv'; document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url),1000); setNotice('Your processed CSV is ready. Download complete.') } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not export this dataset.') } finally { setBusy(false) }
  }
  const operationsCount = metadata?.history.filter(entry => entry.operation !== 'upload').length ?? 0
  const navigate = (next: Section) => { setSection(next); setMobileOpen(false) }
  return <div className="app-shell">
    <aside className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}><a className="brand" href="#" onClick={event => { event.preventDefault(); navigate(metadata ? 'dataset' : 'upload') }} aria-label="DataFlow home"><span className="brand-mark"><Layers3 size={22} /></span>Data<span>Flow</span><span className="brand-dot">.</span></a><button className="mobile-close icon-button" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><X size={20} /></button><div className="sidebar-label">WORKSPACE</div><nav aria-label="Main navigation">{navigation.map(({ key,label,icon: Icon }) => <button key={key} className={`nav-item ${section === key ? 'active' : ''}`} disabled={key !== 'upload' && !metadata} onClick={() => navigate(key)}><Icon size={19} strokeWidth={1.7} /><span>{label}</span>{section === key && <span className="active-dot" />}</button>)}</nav><div className="sidebar-bottom"><div className="sidebar-note"><Leaf size={18} /><strong>A fresh perspective<br />for your data.</strong><p>Less busywork.<br />More possibilities.</p></div><div className="workspace-label"><span className="workspace-avatar">DF</span><div><strong>Personal workspace</strong><span>Local session</span></div><ChevronRight size={14} /></div></div></aside>
    {mobileOpen && <div className="sidebar-overlay" onClick={() => setMobileOpen(false)} />}
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="mobile-menu icon-button" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><Menu size={22} /></button><span>Workspace</span><ChevronRight size={13} /><strong>{navigation.find(item => item.key === section)?.label}</strong></div><div className="topbar-right"><span className="session-indicator"><i /> Temporary session</span><span className="topbar-divider" /><span className="avatar">D</span></div></header>
      <main className="main-content">
        {error && <div className="error-banner" role="alert"><span>{error}</span><button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><X size={17} /></button></div>}
        {notice && section !== 'upload' && <div className="notice-banner" role="status"><Check size={16} /><span>{notice}</span><button className="icon-button" aria-label="Dismiss notification" onClick={() => setNotice('')}><X size={15} /></button></div>}
        {section === 'upload' ? <UploadZone busy={busy} maxUploadMb={uploadLimit} onUpload={file => load(() => api.uploadDataset(file))} onDemo={() => load(api.loadDemo)} /> : metadata && <>
          <div className="page-heading"><div><span className="eyebrow">YOUR DATA WORKSPACE</span><h1>{sectionCopy[section].title}</h1><p>{sectionCopy[section].text}</p></div><div className="heading-actions"><button className="button button-secondary" disabled={busy || !operationsCount} onClick={() => void undo()}>{busy ? <LoaderCircle size={14} className="spin" /> : <Undo2 size={14} />} Undo</button><button className="button button-secondary" onClick={() => navigate('upload')}><Upload size={15} /> Upload new <ArrowUpRight size={14} /></button></div></div>
          <section className="dataset-header"><div className="dataset-file"><div className="dataset-file-icon"><FileSpreadsheet size={25} strokeWidth={1.5} /></div><div><h2>{metadata.filename}</h2><span><span className="format-tag">CSV</span>{size(metadata.file_size)}<span className="dot-separator">·</span>{operationsCount ? `${operationsCount} ${operationsCount === 1 ? 'operation' : 'operations'} applied` : 'Original dataset'}</span></div></div><div className="dataset-health"><Check size={13} /> Ready to explore</div></section>
          <div className="metric-grid">{[{label:'TOTAL ROWS',value:metadata.rows,icon:Database,detail:'Records in your dataset'},{label:'COLUMNS',value:metadata.column_count,icon:Table2,detail:'Fields to explore'},{label:'MISSING VALUES',value:metadata.missing_values,icon:Layers3,detail:metadata.missing_values ? 'A little room for cleanup' : 'Every cell accounted for'},{label:'DUPLICATE ROWS',value:metadata.duplicate_rows,icon:ArrowLeftRight,detail:metadata.duplicate_rows ? 'Repeated records found' : 'All records are unique'}].map(item => <div className="metric-card" key={item.label}><div><span>{item.label}</span><item.icon size={16} strokeWidth={1.5} /></div><strong>{item.value.toLocaleString()}</strong><p>{item.detail}</p></div>)}</div>
          {section === 'dataset' && <><DatasetTable metadata={metadata} preview={preview} loading={previewLoading} page={page} onPage={setPage} /><StatisticsPanel statistics={statistics} /></>}
          {(section === 'clean' || section === 'transform') && <><div className="tool-layout"><OperationForm key={section} metadata={metadata} mode={section} busy={busy} onApply={apply} /><HistoryPanel metadata={metadata} busy={busy} onUndo={undo} /></div>{section === 'transform' && <AssistantPanel metadata={metadata} busy={busy} onApply={applyBatch} />}<div className="processing-preview"><DatasetTable metadata={metadata} preview={preview} loading={previewLoading} page={page} onPage={setPage} /></div>{section === 'clean' && <StatisticsPanel statistics={statistics} />}</>}
          {section === 'visualize' && <><Suspense fallback={<div className="card chart-empty-state"><LoaderCircle size={25} className="spin" /><p className="chart-empty-copy">Opening your chart workspace…</p></div>}><ChartPanel metadata={metadata} /></Suspense><div className="processing-preview"><DatasetTable metadata={metadata} preview={preview} loading={previewLoading} page={page} onPage={setPage} /></div></>}
          {section === 'export' && <div className="tool-layout export-layout"><ExportPanel metadata={metadata} busy={busy} onDownload={download} /><HistoryPanel metadata={metadata} busy={busy} onUndo={undo} /></div>}
        </>}
        <footer className="page-footer"><span><span className="footer-mark">✳</span> A little structure. A lot of possibility.</span><span>Made for curious minds.</span></footer>
      </main>
    </div>
  </div>
}
