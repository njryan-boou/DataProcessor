import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Bot, CheckCheck, LoaderCircle, Sparkles } from 'lucide-react'
import { getAssistantStatus, planOperations } from '../services/api'
import type { AssistantPlan, AssistantStatus, DatasetMetadata, Operation } from '../types'

interface Props { metadata: DatasetMetadata; busy: boolean; onApply: (operations: Operation[]) => Promise<boolean> }
export default function AssistantPanel({ metadata, busy, onApply }: Props) {
  const [prompt, setPrompt] = useState('')
  const [plan, setPlan] = useState<AssistantPlan | null>(null)
  const [status, setStatus] = useState<AssistantStatus | null>(null)
  const [planning, setPlanning] = useState(false)
  const [error, setError] = useState('')
  const request = useRef(0)
  useEffect(() => { getAssistantStatus().then(setStatus).catch(() => setStatus(null)) }, [])
  useEffect(() => { request.current += 1; setPlan(null); setError(''); setPlanning(false) }, [metadata.id, metadata.version])
  const makePlan = async (event: React.FormEvent) => {
    event.preventDefault(); if (!prompt.trim()) return; const token = ++request.current; setPlanning(true); setError(''); setPlan(null)
    try { const result = await planOperations(metadata.id, prompt.trim()); if (token === request.current) setPlan(result) } catch (cause) { if (token === request.current) setError(cause instanceof Error ? cause.message : 'Could not understand this request.') } finally { if (token === request.current) setPlanning(false) }
  }
  const local = status?.provider === 'local'
  return <section className="card assistant-card"><div className="card-header"><div><div className="card-title"><Bot size={19} /><h2>Say it in your own words</h2><span className="badge">{local ? 'Local parser' : status?.provider ? 'AI assistant' : 'Optional assistant'}</span></div><p>Describe your changes. Review the plan before anything is applied.</p></div><Sparkles size={19} className="assistant-spark" /></div>
    <div className="assistant-body">{local && <p className="assistant-local-note">Using a limited local parser. A model provider can be configured for broader natural-language support.</p>}
      <form onSubmit={event => void makePlan(event)}><label className="field"><span className="sr-only">Describe transformations</span><textarea className="input" rows={3} maxLength={2000} required placeholder="Remove duplicates, fill missing age values with the median, and keep rows where salary is greater than 50000." value={prompt} disabled={busy || planning} onChange={event => { setPrompt(event.target.value); setPlan(null) }} /></label><div className="assistant-form-footer"><span>Only supported operations. No arbitrary code.</span><button className="button button-secondary" type="submit" disabled={busy || planning || !prompt.trim()}>{planning ? <LoaderCircle size={14} className="spin" /> : <Sparkles size={14} />}{planning ? 'Planning…' : 'Preview plan'}<ArrowRight size={14} /></button></div></form>
      {error && <p role="alert" className="inline-error">{error}</p>}
      {plan && <div className="assistant-plan"><div className="assistant-plan-heading"><CheckCheck size={17} /><strong>Review your transformation plan</strong><span className="badge">{plan.provider === 'local' ? 'Local parser' : plan.provider}</span></div><p>{plan.explanation}</p><ol>{plan.operations.map((operation, index) => <li key={index}><span className="plan-step">{index + 1}</span><div><strong>{operation.operation.replace(/_/g,' ')}</strong><code>{Object.entries(operation.parameters).map(([key,value]) => `${key.replace(/_/g,' ')}: ${typeof value === 'string' ? value : JSON.stringify(value)}`).join(' · ') || 'All rows'}</code></div></li>)}</ol><div className="assistant-plan-footer"><span>{plan.operations.length} {plan.operations.length === 1 ? 'operation' : 'operations'} · validated by the backend</span><button className="button button-primary" disabled={busy || !plan.operations.length} onClick={() => void onApply(plan.operations)}>{busy ? <LoaderCircle size={14} className="spin" /> : <CheckCheck size={14} />} Apply this plan</button></div></div>}
    </div>
  </section>
}
