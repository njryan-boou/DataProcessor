import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import OperationForm from './OperationForm'
import { dataset } from '../test-fixtures'
import type { DatasetMetadata } from '../types'

function setup(mode: 'clean' | 'transform' = 'transform', metadata: DatasetMetadata = dataset) {
  const onApply = vi.fn().mockResolvedValue(undefined)
  const view = render(<OperationForm metadata={metadata} mode={mode} busy={false} onApply={onApply} />)
  return { ...view, onApply, user: userEvent.setup() }
}

async function chooseOperation(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.selectOptions(screen.getByRole('combobox', { name: 'Choose an operation' }), name)
}

describe('OperationForm', () => {
  it('submits duplicate removal as a generic operation without unrelated parameters', async () => {
    const { user, onApply } = setup('clean')
    await chooseOperation(user, 'remove_duplicates')
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(onApply).toHaveBeenCalledWith({ operation: 'remove_duplicates', parameters: {} })
  })

  it('fills a selected numeric column using a median operation', async () => {
    const { user, onApply } = setup('clean')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Column' }), 'age')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Fill method' }), 'median')
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(onApply).toHaveBeenCalledWith({ operation: 'fill_missing', parameters: { column: 'age', method: 'median' } })
  })

  it('parses custom numeric replacements as numbers', async () => {
    const { user, onApply } = setup('clean')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Column' }), 'age')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Fill method' }), 'custom')
    await user.type(screen.getByRole('spinbutton', { name: 'Replacement value' }), '37.5')
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(onApply).toHaveBeenCalledWith({ operation: 'fill_missing', parameters: { column: 'age', method: 'custom', value: 37.5 } })
  })

  it('offers only custom filling for text and preserves the replacement string', async () => {
    const { user, onApply } = setup('clean')
    expect(screen.getByRole('combobox', { name: 'Fill method' })).toHaveValue('custom')
    expect(screen.queryByRole('option', { name: 'Mean' })).not.toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: 'Replacement value' }), 'Unknown name')
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(onApply).toHaveBeenCalledWith({ operation: 'fill_missing', parameters: { column: 'name', method: 'custom', value: 'Unknown name' } })
  })

  it('supports scoped missing-row removal', async () => {
    const { user, onApply } = setup('clean')
    await chooseOperation(user, 'drop_missing')
    await user.click(screen.getByRole('checkbox', { name: 'age numeric' }))
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(onApply).toHaveBeenCalledWith({ operation: 'drop_missing', parameters: { columns: ['age'] } })
  })

  it('constructs a typed numeric filter', async () => {
    const { user, onApply } = setup()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Column' }), 'salary')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Condition' }), '>')
    await user.type(screen.getByRole('spinbutton', { name: 'Value' }), '50000')
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(onApply).toHaveBeenCalledWith({ operation: 'filter', parameters: { column: 'salary', operator: '>', value: 50000 } })
  })

  it('omits the value for an is-missing filter', async () => {
    const { user, onApply } = setup()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Column' }), 'age')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Condition' }), 'is_missing')
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(onApply).toHaveBeenCalledWith({ operation: 'filter', parameters: { column: 'age', operator: 'is_missing' } })
  })

  it('limits text filtering to appropriate conditions', async () => {
    const { user, onApply } = setup()
    expect(screen.queryByRole('option', { name: 'Greater than (>)' })).not.toBeInTheDocument()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Condition' }), 'contains')
    await user.type(screen.getByRole('textbox', { name: 'Value' }), 'Ada')
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(onApply).toHaveBeenCalledWith({ operation: 'filter', parameters: { column: 'name', operator: 'contains', value: 'Ada' } })
  })

  it('uses the displayed default True value for boolean filtering', async () => {
    const metadata: DatasetMetadata = { ...dataset, columns: [{ name: 'active', type: 'boolean', missing: 1, unique: 2 }], column_count: 1 }
    const { user, onApply } = setup('transform', metadata)
    await user.selectOptions(screen.getByRole('combobox', { name: 'Condition' }), '==')
    expect(screen.getByRole('combobox', { name: 'Value' })).toHaveValue('true')
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(onApply).toHaveBeenCalledWith({ operation: 'filter', parameters: { column: 'active', operator: '==', value: true } })
  })

  it('submits descending sort as a boolean parameter', async () => {
    const { user, onApply } = setup()
    await chooseOperation(user, 'sort')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Column' }), 'salary')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Sort order' }), 'descending')
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(onApply).toHaveBeenCalledWith({ operation: 'sort', parameters: { column: 'salary', ascending: false } })
  })

  it('trims a new column name before sending the rename operation', async () => {
    const { user, onApply } = setup()
    await chooseOperation(user, 'rename_column')
    await user.type(screen.getByRole('textbox', { name: 'New column name' }), '  employee_name  ')
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(onApply).toHaveBeenCalledWith({ operation: 'rename_column', parameters: { column: 'name', new_name: 'employee_name' } })
  })

  it('includes the requested column and target type in a conversion', async () => {
    const { user, onApply } = setup()
    await chooseOperation(user, 'convert_type')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Column' }), 'salary')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Convert to' }), 'text')
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(onApply).toHaveBeenCalledWith({ operation: 'convert_type', parameters: { column: 'salary', type: 'text' } })
  })

  it('prevents deleting all columns and permits deleting a subset', async () => {
    const { user, onApply } = setup()
    await chooseOperation(user, 'delete_columns')
    for (const checkbox of screen.getAllByRole('checkbox')) await user.click(checkbox)
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Keep at least one column')
    expect(onApply).not.toHaveBeenCalled()
    await user.click(screen.getByRole('checkbox', { name: 'name text' }))
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(onApply).toHaveBeenCalledWith({ operation: 'delete_columns', parameters: { columns: ['age', 'salary'] } })
  })

  it('prevents selecting an empty subset of columns', async () => {
    const { user, onApply } = setup()
    await chooseOperation(user, 'select_columns')
    for (const checkbox of screen.getAllByRole('checkbox')) await user.click(checkbox)
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Select at least one column')
    expect(onApply).not.toHaveBeenCalled()
  })

  it('removes deleted columns from a pending column selection', async () => {
    const { user, onApply, rerender } = setup()
    await chooseOperation(user, 'delete_columns')
    await user.click(screen.getByRole('checkbox', { name: 'age numeric' }))
    rerender(<OperationForm metadata={{ ...dataset, version: 2, columns: dataset.columns.filter(column => column.name !== 'age'), column_count: 2 }} mode="transform" busy={false} onApply={onApply} />)
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Select at least one column')
    expect(onApply).not.toHaveBeenCalled()
  })

  it('does not offer numeric columns for text case changes', async () => {
    const { user, onApply } = setup()
    await chooseOperation(user, 'change_case')
    expect(screen.getByRole('combobox', { name: 'Column' })).toHaveValue('name')
    expect(screen.queryByRole('option', { name: 'age · numeric' })).not.toBeInTheDocument()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Text case' }), 'lower')
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    expect(onApply).toHaveBeenCalledWith({ operation: 'change_case', parameters: { column: 'name', case: 'lower' } })
  })
})
