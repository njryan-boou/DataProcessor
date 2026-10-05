import { useRef, useState } from 'react'
import { ArrowUpRight, FileSpreadsheet, LoaderCircle, UploadCloud } from 'lucide-react'

interface Props { onUpload: (file: File) => Promise<void>; onDemo: () => Promise<void>; busy: boolean; maxUploadMb?: number }
export default function UploadZone({ onUpload, onDemo, busy, maxUploadMb = 20 }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const accept = async (file?: File) => {
    setDragging(false)
    if (!file || busy) return
    if (!file.name.toLowerCase().endsWith('.csv')) { setError('Please choose a CSV file. XLSX and JSON support is coming later.'); return }
    if (file.size > maxUploadMb * 1024 * 1024) { setError(`This file exceeds the ${maxUploadMb} MB upload limit. Please choose a smaller CSV.`); return }
    setError('')
    await onUpload(file)
    if (input.current) input.current.value = ''
  }
  return <div className="upload-section">
    <div className="upload-intro"><span className="eyebrow">FROM RAW DATA TO REAL INSIGHT</span><h1>Good decisions start<br />with <span>better data.</span></h1><p>A little less spreadsheet wrangling. A lot more clarity.<br className="desktop-break" /> Bring your data in, and make it work for you.</p></div>
    <div className={`upload-zone ${dragging ? 'dragging' : ''}`} onDragOver={event => { event.preventDefault(); if (!busy) setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); void accept(event.dataTransfer.files[0]) }}>
      <div className="upload-symbol">{busy ? <LoaderCircle className="spin" size={30} /> : <UploadCloud size={30} strokeWidth={1.5} />}</div>
      <h2>{busy ? 'Getting your data ready…' : 'Drop your dataset here'}</h2><p>{busy ? 'Parsing your file and finding the useful details.' : 'Drag and drop a CSV file, or choose one from your device.'}</p>
      <input ref={input} type="file" accept=".csv,text/csv" aria-label="Upload CSV file" className="sr-only" disabled={busy} onChange={event => void accept(event.target.files?.[0])} />
      <button className="button button-primary" disabled={busy} onClick={() => input.current?.click()}><FileSpreadsheet size={16} /> Choose a file <ArrowUpRight size={16} /></button>
      <span className="upload-note">CSV files · Up to {maxUploadMb} MB · Your original stays intact</span>
      {error && <p className="inline-error" role="alert">{error}</p>}
    </div>
    <div className="demo-card"><div className="demo-icon"><FileSpreadsheet size={23} /></div><div><h3>Just taking a look?</h3><p>Explore DataFlow with a sample employee dataset.</p></div><button className="text-button" disabled={busy} onClick={() => void onDemo()}>Load sample dataset <ArrowUpRight size={16} /></button></div>
    <div className="workflow-grid">{[{n:'01',title:'Understand your data',text:'See types, missing values, and statistics at a glance.'},{n:'02',title:'Make it meaningful',text:'Clean and transform with a clear, reversible history.'},{n:'03',title:'Find the bigger picture',text:'Turn your columns into charts and export with confidence.'}].map(item => <div className="workflow-card" key={item.n}><span>{item.n}</span><h3>{item.title}</h3><p>{item.text}</p></div>)}</div>
  </div>
}
