import { describe, expect, it } from 'vitest'
import { chartCanGenerate, validColumns, validSelection } from './chartUtils'
import { dataset } from '../test-fixtures'
import type { ColumnInfo } from '../types'

const columns: ColumnInfo[] = [...dataset.columns, { name: 'date', type: 'datetime', missing: 0, unique: 123 }, { name: 'active', type: 'boolean', missing: 0, unique: 2 }]

describe('chart selection', () => {
  it.each(['histogram', 'box', 'scatter'] as const)('requires numeric X for %s', kind => {
    expect(validColumns(columns, kind, 'x').map(column => column.name)).toEqual(['age', 'salary'])
  })

  it('allows numeric and datetime X for lines, with only numeric Y', () => {
    expect(validColumns(columns, 'line', 'x').map(column => column.name)).toEqual(['age', 'salary', 'date'])
    expect(validColumns(columns, 'line', 'y').map(column => column.name)).toEqual(['age', 'salary'])
  })

  it('uses categorical X and optional numeric aggregation for bars', () => {
    expect(validColumns(columns, 'bar', 'x').map(column => column.name)).toEqual(['name', 'active'])
    expect(validColumns(columns, 'bar', 'y').map(column => column.name)).toEqual(['age', 'salary'])
    expect(validSelection(columns, 'bar')).toEqual({ x: 'name', y: '' })
    expect(chartCanGenerate('bar', { x: 'name', y: '' })).toBe(true)
  })

  it('selects different numeric columns for scatter when available', () => {
    expect(validSelection(columns, 'scatter')).toEqual({ x: 'age', y: 'salary' })
  })

  it('preserves selections when they remain compatible', () => {
    expect(validSelection(columns, 'line', { x: 'date', y: 'salary' })).toEqual({ x: 'date', y: 'salary' })
  })

  it('replaces deleted or converted column selections', () => {
    const changed: ColumnInfo[] = [{ name: 'salary', type: 'numeric', missing: 0, unique: 87 }, { name: 'age', type: 'text', missing: 0, unique: 45 }]
    expect(validSelection(changed, 'scatter', { x: 'age', y: 'deleted' })).toEqual({ x: 'salary', y: 'salary' })
  })

  it('does not permit generating a chart without required axes', () => {
    expect(chartCanGenerate('histogram', { x: '', y: '' })).toBe(false)
    expect(chartCanGenerate('scatter', { x: 'age', y: '' })).toBe(false)
    expect(chartCanGenerate('line', { x: 'date', y: '' })).toBe(false)
    expect(chartCanGenerate('histogram', { x: 'age', y: '' })).toBe(true)
  })

  it('handles datasets without compatible columns', () => {
    expect(validSelection([columns[0]], 'scatter')).toEqual({ x: '', y: '' })
    expect(validColumns(columns, 'histogram', 'y')).toEqual([])
    expect(validColumns(columns, 'box', 'y')).toEqual([])
  })
})
