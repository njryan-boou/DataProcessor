import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import HistoryPanel from './HistoryPanel'
import { dataset } from '../test-fixtures'
import type { DatasetMetadata, HistoryEntry } from '../types'

const upload: HistoryEntry = {
  id: 'upload', operation: 'upload', parameters: {}, description: 'Uploaded team.csv', created_at: '2026-01-01T12:00:00Z',
}
const removeDuplicates: HistoryEntry = {
  id: 'remove-duplicates', operation: 'remove_duplicates', parameters: {}, description: 'Removed duplicate rows', created_at: '2026-01-01T12:01:00Z',
}
const fillMissing: HistoryEntry = {
  id: 'fill-missing', operation: 'fill_missing', parameters: { column: 'age', method: 'median' }, description: 'Filled missing age values with median', created_at: '2026-01-01T12:02:00Z',
}
const withHistory: DatasetMetadata = { ...dataset, history: [upload, removeDuplicates, fillMissing] }

describe('HistoryPanel', () => {
  it('lists and counts only transformations while keeping the original upload visible', () => {
    render(<HistoryPanel metadata={withHistory} busy={false} onUndo={vi.fn().mockResolvedValue(undefined)} />)

    expect(screen.getByText('2', { selector: '.badge' })).toBeInTheDocument()
    const entries = screen.getAllByRole('listitem')
    expect(entries).toHaveLength(3)
    expect(within(entries[0]).getByText('Original dataset uploaded')).toBeInTheDocument()
    expect(within(entries[0]).getByText('Preserved')).toBeInTheDocument()
    expect(within(entries[1]).getByText('Removed duplicate rows')).toBeInTheDocument()
    expect(within(entries[1]).getByText('Step 1', { exact: false })).toBeInTheDocument()
    expect(within(entries[2]).getByText('Filled missing age values with median')).toBeInTheDocument()
    expect(within(entries[2]).getByText('Step 2', { exact: false })).toBeInTheDocument()
    expect(screen.queryByText(upload.description)).not.toBeInTheDocument()
  })

  it('requests undo of the last transformation', async () => {
    const onUndo = vi.fn().mockResolvedValue(undefined)
    render(<HistoryPanel metadata={withHistory} busy={false} onUndo={onUndo} />)

    await userEvent.click(screen.getByRole('button', { name: 'Undo last' }))

    expect(onUndo).toHaveBeenCalledOnce()
  })

  it.each([{ history: [] as HistoryEntry[] }, { history: [upload] }])('prevents undo when no transformation exists ($history)', async ({ history }) => {
    const onUndo = vi.fn().mockResolvedValue(undefined)
    render(<HistoryPanel metadata={{ ...dataset, history }} busy={false} onUndo={onUndo} />)

    expect(screen.getByText('0', { selector: '.badge' })).toBeInTheDocument()
    expect(screen.getByText(/Applied transformations will appear in this history/)).toBeInTheDocument()
    const undoButton = screen.getByRole('button', { name: 'Undo last' })
    expect(undoButton).toBeDisabled()
    await userEvent.click(undoButton)
    expect(onUndo).not.toHaveBeenCalled()
  })

  it('prevents a second undo while a request is running', async () => {
    const onUndo = vi.fn().mockResolvedValue(undefined)
    render(<HistoryPanel metadata={withHistory} busy onUndo={onUndo} />)

    const undoButton = screen.getByRole('button', { name: 'Undo last' })
    expect(undoButton).toBeDisabled()
    await userEvent.click(undoButton)
    expect(onUndo).not.toHaveBeenCalled()
  })
})
