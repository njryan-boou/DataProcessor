import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AssistantPanel from './AssistantPanel'
import { dataset } from '../test-fixtures'
import { getAssistantStatus, planOperations } from '../services/api'
import type { AssistantPlan } from '../types'

vi.mock('../services/api', async importOriginal => ({
  ...await importOriginal<typeof import('../services/api')>(),
  getAssistantStatus: vi.fn(),
  planOperations: vi.fn(),
}))

const plan: AssistantPlan = {
  provider: 'local',
  explanation: 'Remove repeated rows, then fill missing ages.',
  operations: [
    { operation: 'remove_duplicates', parameters: {} },
    { operation: 'fill_missing', parameters: { column: 'age', method: 'median' } },
  ],
}

async function requestPlan() {
  await userEvent.type(screen.getByRole('textbox', { name: 'Describe transformations' }), '  Remove duplicates  ')
  await userEvent.click(screen.getByRole('button', { name: 'Preview plan' }))
}

describe('AssistantPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getAssistantStatus).mockResolvedValue({ provider: 'local', available: true })
    vi.mocked(planOperations).mockResolvedValue(plan)
  })

  it('previews supported operations and applies them only after explicit review', async () => {
    const onApply = vi.fn().mockResolvedValue(true)
    render(<AssistantPanel metadata={dataset} busy={false} onApply={onApply} />)

    await requestPlan()

    expect(planOperations).toHaveBeenCalledWith(dataset.id, 'Remove duplicates')
    expect(await screen.findByText('Review your transformation plan')).toBeInTheDocument()
    expect(screen.getByText('remove duplicates')).toBeInTheDocument()
    expect(screen.getByText('column: age · method: median')).toBeInTheDocument()
    expect(onApply).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Apply this plan' }))
    expect(onApply).toHaveBeenCalledOnce()
    expect(onApply).toHaveBeenCalledWith(plan.operations)
  })

  it('shows a planning error without exposing an apply action', async () => {
    vi.mocked(planOperations).mockRejectedValue(new Error('Column "ages" does not exist.'))
    const onApply = vi.fn().mockResolvedValue(true)
    render(<AssistantPanel metadata={dataset} busy={false} onApply={onApply} />)

    await requestPlan()

    expect(await screen.findByRole('alert')).toHaveTextContent('Column "ages" does not exist.')
    expect(screen.queryByRole('button', { name: 'Apply this plan' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Preview plan' })).toBeEnabled()
    expect(onApply).not.toHaveBeenCalled()
  })

  it('invalidates a reviewed plan when the dataset version changes', async () => {
    const onApply = vi.fn().mockResolvedValue(true)
    const { rerender } = render(<AssistantPanel metadata={dataset} busy={false} onApply={onApply} />)
    await requestPlan()
    await screen.findByRole('button', { name: 'Apply this plan' })

    rerender(<AssistantPanel metadata={{ ...dataset, version: dataset.version + 1 }} busy={false} onApply={onApply} />)

    expect(screen.queryByText('Review your transformation plan')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Apply this plan' })).not.toBeInTheDocument()
    expect(onApply).not.toHaveBeenCalled()
  })

  it('discards a plan that finishes after the dataset changed', async () => {
    let finishPlan!: (value: AssistantPlan) => void
    vi.mocked(planOperations).mockReturnValue(new Promise(resolve => { finishPlan = resolve }))
    const onApply = vi.fn().mockResolvedValue(true)
    const { rerender } = render(<AssistantPanel metadata={dataset} busy={false} onApply={onApply} />)
    await requestPlan()
    expect(screen.getByRole('button', { name: 'Planning…' })).toBeDisabled()

    rerender(<AssistantPanel metadata={{ ...dataset, version: dataset.version + 1 }} busy={false} onApply={onApply} />)
    await act(async () => { finishPlan(plan) })

    expect(screen.queryByText('Review your transformation plan')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Apply this plan' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Preview plan' })).toBeEnabled()
    expect(onApply).not.toHaveBeenCalled()
  })

  it('disables preview and applying an existing plan while an operation is running', async () => {
    const onApply = vi.fn().mockResolvedValue(true)
    const { rerender } = render(<AssistantPanel metadata={dataset} busy={false} onApply={onApply} />)
    await requestPlan()
    await screen.findByRole('button', { name: 'Apply this plan' })

    rerender(<AssistantPanel metadata={dataset} busy onApply={onApply} />)

    expect(screen.getByRole('textbox', { name: 'Describe transformations' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Preview plan' })).toBeDisabled()
    const applyButton = screen.getByRole('button', { name: 'Apply this plan' })
    expect(applyButton).toBeDisabled()
    await userEvent.click(applyButton)
    expect(onApply).not.toHaveBeenCalled()
  })

  it('keeps manual transformation planning available when provider status cannot load', async () => {
    vi.mocked(getAssistantStatus).mockRejectedValue(new Error('Status unavailable'))
    render(<AssistantPanel metadata={dataset} busy={false} onApply={vi.fn().mockResolvedValue(true)} />)
    await requestPlan()
    await waitFor(() => expect(screen.getByText('Review your transformation plan')).toBeInTheDocument())
    expect(screen.getByText('Optional assistant')).toBeInTheDocument()
  })
})
