import { useEffect, useRef, useState } from 'react';
import { BarChart3, ChartNoAxesCombined, LoaderCircle, Sparkles } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getChart } from '../services/api';
import type { ChartData, ChartKind, DatasetMetadata } from '../types';
import { chartCanGenerate, validColumns, validSelection } from './chartUtils';

const chartKinds: Array<{ kind: ChartKind; label: string; description: string }> = [
  { kind: 'histogram', label: 'Histogram', description: 'Understand how numeric values are distributed.' },
  { kind: 'bar', label: 'Bar chart', description: 'Compare category counts or average numeric values.' },
  { kind: 'line', label: 'Line chart', description: 'Follow a numeric measure across time or another numeric column.' },
  { kind: 'scatter', label: 'Scatter plot', description: 'Explore the relationship between two numeric columns.' },
  { kind: 'box', label: 'Box plot', description: 'See the median, quartiles, spread, and potential outliers.' },
];

const formatNumber = (value: number) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value);
const gridColor = 'var(--border, #e6e9ee)';
const mutedColor = 'var(--muted, #778091)';
const chartColor = '#8ba966';
const tooltipStyle = {
  borderRadius: 10,
  border: '1px solid #e1e8d8',
  boxShadow: '0 6px 24px #19213b12',
  fontSize: 12,
};

function BoxPlot({ points, column }: { points: ChartData['points']; column: string }) {
  const boxes = points.filter((point) => ['min', 'q1', 'median', 'q3', 'max'].every((key) => Number.isFinite(Number(point[key]))));
  if (!boxes.length) return <div className="chart-empty">This column has no numeric values to plot.</div>;
  const values = boxes.flatMap((point) => [Number(point.min), Number(point.max), ...(Array.isArray(point.outliers) ? point.outliers.filter((value: unknown) => typeof value === 'number' && Number.isFinite(value)) : [])]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding = max === min ? Math.max(Math.abs(min) * 0.1, 1) : (max - min) * 0.12;
  const low = min - padding;
  const high = max + padding;
  const y = (value: number) => 288 - ((value - low) / (high - low)) * 250;
  return (
    <svg viewBox="0 0 860 345" width="100%" role="img" aria-label={`Box plot for ${column}; boxes show quartiles, horizontal lines show medians, whiskers show the non-outlier range, and dots show outliers.`} style={{ display: 'block', minHeight: 260 }}>
      {Array.from({ length: 6 }, (_, index) => {
        const value = low + ((high - low) * index) / 5;
        return <g key={index}>
          <line x1="76" x2="835" y1={y(value)} y2={y(value)} stroke={gridColor} strokeDasharray="3 4" />
          <text x="65" y={y(value) + 4} textAnchor="end" fontSize="11" fill={mutedColor}>{formatNumber(value)}</text>
        </g>;
      })}
      {boxes.map((point, index) => {
        const center = 76 + ((index + 0.5) * 759) / boxes.length;
        const halfWidth = Math.min(65, 280 / boxes.length);
        const outliers: number[] = Array.isArray(point.outliers) ? point.outliers : [];
        return <g key={index}>
          <title>{`${point.label ?? column}: min ${formatNumber(Number(point.min))}, Q1 ${formatNumber(Number(point.q1))}, median ${formatNumber(Number(point.median))}, Q3 ${formatNumber(Number(point.q3))}, max ${formatNumber(Number(point.max))}`}</title>
          <line x1={center} x2={center} y1={y(Number(point.min))} y2={y(Number(point.max))} stroke={chartColor} strokeWidth="2" />
          <line x1={center - halfWidth / 2} x2={center + halfWidth / 2} y1={y(Number(point.min))} y2={y(Number(point.min))} stroke={chartColor} strokeWidth="2" />
          <line x1={center - halfWidth / 2} x2={center + halfWidth / 2} y1={y(Number(point.max))} y2={y(Number(point.max))} stroke={chartColor} strokeWidth="2" />
          <rect x={center - halfWidth} y={y(Number(point.q3))} width={halfWidth * 2} height={Math.max(1, y(Number(point.q1)) - y(Number(point.q3)))} fill="#eaf3db" stroke={chartColor} strokeWidth="2" rx="3" />
          <line x1={center - halfWidth} x2={center + halfWidth} y1={y(Number(point.median))} y2={y(Number(point.median))} stroke="#57743a" strokeWidth="3" />
          {outliers.filter(Number.isFinite).map((value, outlierIndex) => <circle key={outlierIndex} cx={center} cy={y(value)} r="3.5" fill={chartColor} fillOpacity="0.6"><title>Outlier: {formatNumber(value)}</title></circle>)}
          <text x={center} y="313" textAnchor="middle" fontSize="12" fill={mutedColor}>{String(point.label ?? column)}</text>
        </g>;
      })}
    </svg>
  );
}

function ChartView({ data, kind, x, y, datetime }: { data: ChartData; kind: ChartKind; x: string; y: string; datetime: boolean }) {
  if (kind === 'box') return <BoxPlot points={data.points} column={x} />;
  if (kind === 'scatter') return <ResponsiveContainer width="100%" height={340}>
    <ScatterChart margin={{ top: 16, right: 20, bottom: 28, left: 8 }}>
      <CartesianGrid stroke={gridColor} strokeDasharray="3 4" />
      <XAxis dataKey="x" name={x} type="number" tick={{ fill: mutedColor, fontSize: 11 }} axisLine={false} tickLine={false} label={{ value: x, position: 'bottom', offset: 12, fill: mutedColor, fontSize: 12 }} />
      <YAxis dataKey="y" name={y} type="number" tick={{ fill: mutedColor, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={formatNumber} />
      <Tooltip cursor={{ strokeDasharray: '3 3' }} contentStyle={tooltipStyle} />
      <Scatter name={`${y} by ${x}`} data={data.points} fill={chartColor} fillOpacity={0.75} />
    </ScatterChart>
  </ResponsiveContainer>;
  if (kind === 'line') return <ResponsiveContainer width="100%" height={340}>
    <LineChart data={datetime ? data.points.map((point) => ({ ...point, x: new Date(String(point.x)).getTime() })) : data.points} margin={{ top: 16, right: 20, bottom: 28, left: 8 }}>
      <CartesianGrid stroke={gridColor} strokeDasharray="3 4" vertical={false} />
      <XAxis dataKey="x" type="number" domain={['dataMin', 'dataMax']} tickFormatter={(value: number) => datetime ? new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : formatNumber(value)} tick={{ fill: mutedColor, fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={30} label={{ value: x, position: 'bottom', offset: 12, fill: mutedColor, fontSize: 12 }} />
      <YAxis tick={{ fill: mutedColor, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={formatNumber} />
      <Tooltip contentStyle={tooltipStyle} labelFormatter={(value: unknown) => datetime ? new Date(Number(value)).toLocaleString() : String(value)} />
      <Line type="linear" dataKey="y" name={y} stroke={chartColor} strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} />
    </LineChart>
  </ResponsiveContainer>;
  const points = data.points.map((point) => ({ ...point, label: point.label ?? point.bin ?? point.x, value: point.value ?? point.count ?? point.y }));
  return <ResponsiveContainer width="100%" height={340}>
    <BarChart data={points} margin={{ top: 16, right: 20, bottom: 28, left: 8 }} barCategoryGap={kind === 'histogram' ? '8%' : '35%'}>
      <CartesianGrid stroke={gridColor} strokeDasharray="3 4" vertical={false} />
      <XAxis dataKey="label" tick={{ fill: mutedColor, fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={20} label={{ value: x, position: 'bottom', offset: 12, fill: mutedColor, fontSize: 12 }} />
      <YAxis tick={{ fill: mutedColor, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={formatNumber} allowDecimals={Boolean(y && kind === 'bar')} />
      <Tooltip contentStyle={tooltipStyle} cursor={{ fill: '#8ba96609' }} />
      <Bar dataKey="value" name={kind === 'histogram' || !y ? 'Count' : `Average ${y}`} fill={chartColor} radius={[4, 4, 0, 0]} maxBarSize={75} />
    </BarChart>
  </ResponsiveContainer>;
}

export default function ChartPanel({ metadata }: { metadata: DatasetMetadata }) {
  const [kind, setKind] = useState<ChartKind>('histogram');
  const [selection, setSelection] = useState(() => validSelection(metadata.columns, 'histogram'));
  const [chart, setChart] = useState<ChartData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const requestId = useRef(0);
  const columnSignature = JSON.stringify(metadata.columns.map(({ name, type }) => ({ name, type })));

  useEffect(() => {
    requestId.current += 1;
    setLoading(false);
    setChart(null);
    setError('');
    setSelection((current) => validSelection(metadata.columns, kind, current));
  }, [kind, metadata.id, metadata.version, columnSignature]);

  const selected = validSelection(metadata.columns, kind, selection);
  const xColumns = validColumns(metadata.columns, kind, 'x');
  const yColumns = validColumns(metadata.columns, kind, 'y');
  const description = chartKinds.find((item) => item.kind === kind)?.description;
  const chartNotes = chart ? [
    typeof chart.omitted_rows === 'number' && chart.omitted_rows > 0 ? `${chart.omitted_rows.toLocaleString()} rows with missing or non-finite values excluded.` : '',
    typeof chart.excluded_categories === 'number' && chart.excluded_categories > 0 ? `Showing the 30 most frequent categories; ${chart.excluded_categories.toLocaleString()} others excluded.` : '',
    chart.sampled && !chart.excluded_categories ? 'A representative sample is shown to keep the chart responsive.' : '',
  ].filter(Boolean).join(' ') : '';

  function updateSelection(axis: 'x' | 'y', value: string) {
    requestId.current += 1;
    setLoading(false);
    setChart(null);
    setError('');
    setSelection({ ...selected, [axis]: value });
  }

  async function generate() {
    const id = ++requestId.current;
    setLoading(true);
    setError('');
    try {
      const result = await getChart(metadata.id, kind, selected.x, selected.y || undefined);
      if (requestId.current === id) setChart(result);
    } catch (cause) {
      if (requestId.current === id) {
        setChart(null);
        setError(cause instanceof Error ? cause.message : 'Could not create this chart. Please try again.');
      }
    } finally {
      if (requestId.current === id) setLoading(false);
    }
  }

  return <div className="chart-panel">
    <div className="card chart-builder">
      <div className="chart-title-row">
        <div><div className="eyebrow">CHART BUILDER</div><h3 className="chart-title">Find the story in your data</h3></div>
        <ChartNoAxesCombined size={23} color={chartColor} />
      </div>
      <div className="chart-type-tabs" aria-label="Chart type">
        {chartKinds.map((item) => <button key={item.kind} type="button" onClick={() => setKind(item.kind)} aria-pressed={kind === item.kind} className="button chart-type-button">{item.label}</button>)}
      </div>
      <div className="chart-controls">
        <label className="field chart-field"><span>{kind === 'box' || kind === 'histogram' ? 'Numeric column' : 'X axis'}</span><select className="select" value={selected.x} onChange={(event) => updateSelection('x', event.target.value)} aria-label="Chart X column" disabled={!xColumns.length}>{!xColumns.length && <option value="">No compatible columns</option>}{xColumns.map((column) => <option key={column.name} value={column.name}>{column.name}</option>)}</select></label>
        {kind !== 'histogram' && kind !== 'box' && <label className="field chart-field"><span>{kind === 'bar' ? 'Measure' : 'Y axis'}</span><select className="select" value={selected.y} onChange={(event) => updateSelection('y', event.target.value)} aria-label="Chart Y column" disabled={kind !== 'bar' && !yColumns.length}>{kind === 'bar' && <option value="">Row count</option>}{kind !== 'bar' && !yColumns.length && <option value="">No numeric columns</option>}{yColumns.map((column) => <option key={column.name} value={column.name}>{kind === 'bar' ? `Average ${column.name}` : column.name}</option>)}</select></label>}
        <button className="button button-primary chart-generate" type="button" onClick={generate} disabled={loading || !chartCanGenerate(kind, selected)}>{loading ? <LoaderCircle size={15} className="spin" /> : <Sparkles size={15} />} {loading ? 'Generating…' : 'Generate chart'}</button>
      </div>
      <p className="chart-description">{description}{!xColumns.length ? ' No compatible columns are available; convert a column type in Transform to use this chart.' : ''}</p>
    </div>
    <div className="card chart-canvas">
      {error && <div role="alert" className="chart-error">{error}</div>}
      {chart && !loading && <><div className="chart-canvas-title"><h3>{kind === 'histogram' ? `Distribution of ${selected.x}` : kind === 'box' ? `Spread of ${selected.x}` : kind === 'bar' ? `${selected.y ? `Average ${selected.y}` : 'Row count'} by ${selected.x}` : `${selected.y} by ${selected.x}`}</h3><span className="chart-dataset-badge">Current dataset</span></div>{chart.points.length ? <ChartView data={chart} kind={kind} x={selected.x} y={selected.y} datetime={metadata.columns.find((column) => column.name === selected.x)?.type === 'datetime'} /> : <div className="chart-empty">There are no values to plot. Try another column or adjust your filters.</div>}{kind === 'box' && <p className="chart-box-legend">Box: 25th–75th percentile · center line: median · whiskers: non-outlier range · dots: outliers</p>}{chartNotes && <p className="chart-description">{chartNotes}</p>}</>}
      {!chart && !error && <div className="chart-empty-state">
        <div className="chart-empty-icon">{loading ? <LoaderCircle size={25} color={chartColor} className="spin" /> : <BarChart3 size={25} color={chartColor} />}</div>
        <h3 className="chart-empty-heading">{loading ? 'Building your chart' : 'A fresh perspective on your data'}</h3><p className="chart-empty-copy">{loading ? 'Calculating the values for your selected columns…' : 'Choose a chart type and columns above, then generate a visualization to discover patterns and relationships.'}</p>
      </div>}
    </div>
  </div>;
}
