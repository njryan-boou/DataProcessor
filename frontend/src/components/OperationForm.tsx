import { useEffect, useState } from 'react'
import { ArrowRight, Info, LoaderCircle, Sparkles } from 'lucide-react'
import type { DatasetMetadata, Operation } from '../types'

const tools = {
  remove_duplicates: { label:'Remove duplicate rows',description:'Keep the first occurrence of each complete row and remove identical repeats.' },
  drop_missing: { label:'Remove rows with missing values',description:'Remove rows with empty cells in all or selected columns.' },
  fill_missing: { label:'Fill missing values',description:'Replace empty cells in one column using a statistic or a value of your choice.' },
  trim_whitespace: { label:'Trim whitespace',description:'Remove leading and trailing spaces from text. Spaces within a value stay intact.' },
  detect_outliers: { label:'Detect numeric outliers',description:'Flag unusual numeric values using the interquartile range. No rows are removed.' },
  filter: { label:'Filter rows',description:'Keep only the rows that match a condition. Your original dataset stays intact.' },
  sort: { label:'Sort by column',description:'Put your rows in order using a numeric, text, boolean, or date column.' },
  rename_column: { label:'Rename a column',description:'Give a column a clearer name without changing its values.' },
  delete_columns: { label:'Delete columns',description:'Remove selected columns from your working dataset. You can undo this change.' },
  convert_type: { label:'Convert column type',description:'Convert all non-missing values when possible. Invalid values leave the dataset unchanged.' },
  change_case: { label:'Change text case',description:'Make values in a text column consistently uppercase or lowercase.' },
  select_columns: { label:'Select a subset of columns',description:'Keep only the columns you choose, in their current order.' },
}
type Tool = keyof typeof tools
const cleanTools: Tool[] = ['fill_missing','remove_duplicates','drop_missing','trim_whitespace','detect_outliers']
const transformTools: Tool[] = ['filter','sort','rename_column','convert_type','change_case','delete_columns','select_columns']
const columnless: Tool[] = ['remove_duplicates','drop_missing','trim_whitespace','delete_columns','select_columns']
interface Props { metadata: DatasetMetadata; mode: 'clean' | 'transform'; busy: boolean; onApply: (operation: Operation) => Promise<void> }

export default function OperationForm({ metadata, mode, busy, onApply }: Props) {
  const available = mode === 'clean' ? cleanTools : transformTools
  const [tool, setTool] = useState<Tool>(available[0])
  const [column, setColumn] = useState(metadata.columns[0]?.name ?? '')
  const [method, setMethod] = useState('median')
  const [value, setValue] = useState('')
  const [operator, setOperator] = useState('>')
  const [newName, setNewName] = useState('')
  const [ascending, setAscending] = useState(true)
  const [type, setType] = useState('numeric')
  const [textCase, setTextCase] = useState('upper')
  const [columns, setColumns] = useState<string[]>([])
  const [validation, setValidation] = useState('')
  const eligible = metadata.columns.filter(info => tool === 'detect_outliers' ? info.type === 'numeric' : tool === 'change_case' ? info.type === 'text' : tool === 'fill_missing' ? info.type !== 'datetime' : true)
  const selectedColumn = eligible.find(info => info.name === column) ?? eligible[0]
  const selectedName = selectedColumn?.name ?? ''
  const numeric = selectedColumn?.type === 'numeric'
  const effectiveMethod = numeric ? method : 'custom'
  const operators = selectedColumn?.type === 'text' ? ['==','!=','contains','not_contains','is_missing','not_missing'] : selectedColumn?.type === 'boolean' ? ['==','!=','is_missing','not_missing'] : ['>','>=','<','<=','==','!=','is_missing','not_missing']
  const effectiveOperator = operators.includes(operator) ? operator : operators[0]
  const noValue = ['is_missing','not_missing'].includes(effectiveOperator)
  const signature = metadata.columns.map(info => info.name).join('\0')
  useEffect(() => { setColumns(current => current.filter(name => metadata.columns.some(info => info.name === name))); setValidation('') }, [signature])
  const chooseTool = (next: Tool) => { setTool(next); setValue(''); setNewName(''); setValidation(''); setColumns(next === 'select_columns' ? metadata.columns.map(info => info.name) : []) }
  const toggleColumn = (name: string) => setColumns(current => current.includes(name) ? current.filter(item => item !== name) : [...current,name])
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setValidation('')
    let parameters: Record<string, unknown> = {}
    if (!columnless.includes(tool) && !selectedName) { setValidation('This operation needs a compatible column.'); return }
    if (['delete_columns','select_columns'].includes(tool) && !columns.length) { setValidation('Select at least one column.'); return }
    if (tool === 'delete_columns' && columns.length === metadata.columns.length) { setValidation('Keep at least one column in your dataset.'); return }
    const parsedValue = numeric ? Number(value) : selectedColumn?.type === 'boolean' ? (value || 'true') === 'true' : value
    switch (tool) {
      case 'fill_missing': parameters = { column:selectedName,method:effectiveMethod,...(effectiveMethod === 'custom' ? { value:parsedValue } : {}) }; break
      case 'drop_missing': case 'trim_whitespace': parameters = columns.length ? { columns } : {}; break
      case 'detect_outliers': parameters = { column:selectedName }; break
      case 'filter': parameters = { column:selectedName,operator:effectiveOperator,...(!noValue ? { value:parsedValue } : {}) }; break
      case 'sort': parameters = { column:selectedName,ascending }; break
      case 'rename_column': parameters = { column:selectedName,new_name:newName.trim() }; break
      case 'delete_columns': case 'select_columns': parameters = { columns: metadata.columns.filter(info => columns.includes(info.name)).map(info => info.name) }; break
      case 'convert_type': parameters = { column:selectedName,type }; break
      case 'change_case': parameters = { column:selectedName,case:textCase }; break
    }
    await onApply({ operation:tool,parameters })
  }
  return <section className="card operation-card"><div className="card-header"><div><div className="card-title"><Sparkles size={18} /><h2>{mode === 'clean' ? 'Clean your dataset' : 'Transform your dataset'}</h2></div><p>Small changes. Better data. Everything stays reversible.</p></div><span className="badge">{mode === 'clean' ? '5' : '7'} tools</span></div>
    <form className="operation-form" onSubmit={event => void submit(event)}>
      <label className="field"><span>Choose an operation</span><select className="select" value={tool} onChange={event => chooseTool(event.target.value as Tool)} disabled={busy}>{available.map(name => <option key={name} value={name}>{tools[name].label}</option>)}</select></label>
      <p className="tool-description"><Info size={14} />{tools[tool].description}</p>
      <div className="form-grid">
        {!columnless.includes(tool) && <label className="field"><span>Column</span><select className="select" value={selectedName} onChange={event => { setColumn(event.target.value); setValue('') }} disabled={busy || !eligible.length}>{!eligible.length && <option value="">No compatible columns</option>}{eligible.map(info => <option key={info.name} value={info.name}>{info.name} · {info.type}</option>)}</select></label>}
        {tool === 'fill_missing' && <label className="field"><span>Fill method</span><select className="select" value={effectiveMethod} onChange={event => setMethod(event.target.value)} disabled={busy}>{numeric && <><option value="mean">Mean</option><option value="median">Median</option><option value="zero">Zero</option></>}<option value="custom">Custom value</option></select></label>}
        {tool === 'filter' && <label className="field"><span>Condition</span><select className="select" value={effectiveOperator} onChange={event => setOperator(event.target.value)} disabled={busy}>{operators.map(op => <option value={op} key={op}>{({ '>':'Greater than (>)','>=':'Greater than or equal (≥)','<':'Less than (<)','<=':'Less than or equal (≤)','==':'Equals (=)','!=':'Does not equal (≠)',contains:'Contains',not_contains:'Does not contain',is_missing:'Is missing',not_missing:'Is not missing' } as Record<string,string>)[op]}</option>)}</select></label>}
        {((tool === 'fill_missing' && effectiveMethod === 'custom') || (tool === 'filter' && !noValue)) && <label className="field"><span>{tool === 'fill_missing' ? 'Replacement value' : 'Value'}</span>{selectedColumn?.type === 'boolean' ? <select className="select" value={value || 'true'} onChange={event => setValue(event.target.value)} disabled={busy}><option value="true">True</option><option value="false">False</option></select> : <input className="input" type={numeric ? 'number' : 'text'} step={numeric ? 'any' : undefined} required value={value} onChange={event => setValue(event.target.value)} placeholder={numeric ? 'e.g. 50000' : 'Enter a value'} disabled={busy} />}</label>}
        {tool === 'rename_column' && <label className="field"><span>New column name</span><input className="input" required value={newName} onChange={event => setNewName(event.target.value)} placeholder="e.g. annual_salary" disabled={busy} /></label>}
        {tool === 'sort' && <label className="field"><span>Sort order</span><select className="select" value={ascending ? 'ascending' : 'descending'} onChange={event => setAscending(event.target.value === 'ascending')} disabled={busy}><option value="ascending">Ascending · A → Z, low → high</option><option value="descending">Descending · Z → A, high → low</option></select></label>}
        {tool === 'convert_type' && <label className="field"><span>Convert to</span><select className="select" value={type} onChange={event => setType(event.target.value)} disabled={busy}><option value="numeric">Numeric</option><option value="text">Text</option><option value="boolean">Boolean</option><option value="datetime">Date & time</option></select></label>}
        {tool === 'change_case' && <label className="field"><span>Text case</span><select className="select" value={textCase} onChange={event => setTextCase(event.target.value)} disabled={busy}><option value="upper">UPPERCASE</option><option value="lower">lowercase</option></select></label>}
      </div>
      {['drop_missing','trim_whitespace','delete_columns','select_columns'].includes(tool) && <fieldset className="column-picker"><legend>{tool === 'select_columns' ? 'Columns to keep' : tool === 'delete_columns' ? 'Columns to remove' : 'Columns (leave unselected to use all)'}</legend><div>{metadata.columns.filter(info => tool !== 'trim_whitespace' || info.type === 'text').map(info => <label key={info.name}><input type="checkbox" checked={columns.includes(info.name)} onChange={() => toggleColumn(info.name)} disabled={busy} /><span>{info.name}</span><span className="type-badge">{info.type}</span></label>)}</div></fieldset>}
      {tool === 'detect_outliers' && <p className="operation-hint">Values below Q1 − 1.5 × IQR or above Q3 + 1.5 × IQR are considered potential outliers. Review them in Column insights.</p>}
      {validation && <p className="inline-error" role="alert">{validation}</p>}
      <div className="operation-footer"><span>Changes apply to your working copy.</span><button className="button button-primary" type="submit" disabled={busy || (!columnless.includes(tool) && !selectedName)}>{busy ? <LoaderCircle size={15} className="spin" /> : <Sparkles size={15} />}{busy ? 'Applying…' : 'Apply operation'}<ArrowRight size={15} /></button></div>
    </form>
  </section>
}
