import type { ReactNode } from 'react'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChartPanel from './ChartPanel'
import { getChart } from '../services/api'
import { dataset } from '../test-fixtures'
import type { ChartData } from '../types'

vi.mock('../services/api', () => ({ getChart: vi.fn() }))
// The chart library relies on browser layout. Test controls and API integration
// separately from Recharts' own rendering, using observable chart data here.
vi.mock('recharts', () => {
  const Chart = ({ children, data }: { children?: ReactNode; data?: unknown }) => <div data-testid="rendered-chart">{data ? JSON.stringify(data) : ''}{children}</div>
  const Empty = () => null
  return {
    ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    BarChart: Chart, LineChart: Chart, ScatterChart: Chart,
    Bar: Empty, CartesianGrid: Empty, Line: Empty, Scatter: Empty, Tooltip: Empty, XAxis: Empty, YAxis: Empty,
  }
})

const histogram: ChartData = { kind: 'histogram', x: 'age', points: [{ label: '20 – 30', count: 8 }], omitted_rows: 3, sampled: false }

beforeEach(() => {
  vi.mocked(getChart).mockReset()
  vi.mocked(getChart).mockResolvedValue(histogram)
})

describe('ChartPanel', () => {
  it('waits for Generate and sends a compatible histogram selection', async () => {
    const user = userEvent.setup()
    render(<ChartPanel metadata={dataset} />)
    expect(getChart).not.toHaveBeenCalled()
    expect(screen.getByRole('combobox', { name: 'Chart X column' })).toHaveValue('age')
    expect(screen.queryByRole('combobox', { name: 'Chart Y column' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Generate chart' }))
    expect(getChart).toHaveBeenCalledWith(dataset.id, 'histogram', 'age', undefined)
    expect(await screen.findByRole('heading', { name: 'Distribution of age' })).toBeInTheDocument()
    expect(screen.getByTestId('rendered-chart')).toHaveTextContent('20 – 30')
    expect(screen.getByText(/3 rows with missing or non-finite values excluded/)).toBeInTheDocument()
  })

  it('uses category counts as the default bar measure', async () => {
    const user = userEvent.setup()
    vi.mocked(getChart).mockResolvedValue({ kind: 'bar', x: 'name', points: [{ label: 'Ada', value: 4, count: 4 }] })
    render(<ChartPanel metadata={dataset} />)
    await user.click(screen.getByRole('button', { name: 'Bar chart' }))
    expect(screen.getByRole('combobox', { name: 'Chart X column' })).toHaveValue('name')
    expect(screen.getByRole('combobox', { name: 'Chart Y column' })).toHaveValue('')
    await user.click(screen.getByRole('button', { name: 'Generate chart' }))
    expect(getChart).toHaveBeenCalledWith(dataset.id, 'bar', 'name', undefined)
    expect(await screen.findByRole('heading', { name: 'Row count by name' })).toBeInTheDocument()
  })

  it('requires numeric columns on both scatter axes', async () => {
    const user = userEvent.setup()
    render(<ChartPanel metadata={dataset} />)
    await user.click(screen.getByRole('button', { name: 'Scatter plot' }))
    expect(screen.getByRole('combobox', { name: 'Chart X column' })).toHaveValue('age')
    expect(screen.getByRole('combobox', { name: 'Chart Y column' })).toHaveValue('salary')
    expect(screen.queryByRole('option', { name: 'name' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Generate chart' }))
    expect(getChart).toHaveBeenCalledWith(dataset.id, 'scatter', 'age', 'salary')
  })

  it('disables chart creation when the dataset has no compatible column', () => {
    render(<ChartPanel metadata={{ ...dataset, columns: [dataset.columns[0]], column_count: 1 }} />)
    expect(screen.getByRole('button', { name: 'Generate chart' })).toBeDisabled()
    expect(screen.getByRole('combobox', { name: 'Chart X column' })).toBeDisabled()
    expect(screen.getByText(/No compatible columns are available/)).toBeInTheDocument()
  })

  it('shows backend chart failures without leaving a loading state', async () => {
    const user = userEvent.setup()
    vi.mocked(getChart).mockRejectedValue(new Error('Column age has no finite numeric values to plot.'))
    render(<ChartPanel metadata={dataset} />)
    await user.click(screen.getByRole('button', { name: 'Generate chart' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Column age has no finite numeric values')
    expect(screen.getByRole('button', { name: 'Generate chart' })).toBeEnabled()
  })

  it('invalidates a generated chart when the dataset version changes', async () => {
    const user = userEvent.setup()
    const { rerender } = render(<ChartPanel metadata={dataset} />)
    await user.click(screen.getByRole('button', { name: 'Generate chart' }))
    await screen.findByRole('heading', { name: 'Distribution of age' })
    rerender(<ChartPanel metadata={{ ...dataset, version: 2 }} />)
    expect(screen.queryByTestId('rendered-chart')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'A fresh perspective on your data' })).toBeInTheDocument()
    expect(getChart).toHaveBeenCalledTimes(1)
  })

  it('selects a remaining compatible column after the selected one is deleted', async () => {
    const user = userEvent.setup()
    const { rerender } = render(<ChartPanel metadata={dataset} />)
    rerender(<ChartPanel metadata={{ ...dataset, version: 2, columns: dataset.columns.filter(column => column.name !== 'age'), column_count: 2 }} />)
    expect(screen.getByRole('combobox', { name: 'Chart X column' })).toHaveValue('salary')
    await user.click(screen.getByRole('button', { name: 'Generate chart' }))
    expect(getChart).toHaveBeenCalledWith(dataset.id, 'histogram', 'salary', undefined)
  })

  it('discards an in-flight result after the user changes chart type', async () => {
    const user = userEvent.setup()
    let finish!: (chart: ChartData) => void
    vi.mocked(getChart).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    render(<ChartPanel metadata={dataset} />)
    await user.click(screen.getByRole('button', { name: 'Generate chart' }))
    expect(screen.getByRole('button', { name: 'Generating…' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Bar chart' }))
    await act(async () => finish(histogram))
    expect(screen.queryByTestId('rendered-chart')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate chart' })).toBeEnabled()
    expect(screen.getByRole('combobox', { name: 'Chart X column' })).toHaveValue('name')
  })
})
