import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import UploadZone from './UploadZone'

describe('UploadZone', () => {
  it('accepts a CSV file and lets users load a sample', async () => {
    const onUpload = vi.fn().mockResolvedValue(undefined)
    const onDemo = vi.fn().mockResolvedValue(undefined)
    render(<UploadZone onUpload={onUpload} onDemo={onDemo} busy={false} />)
    const file = new File(['name,age\nAda,32'], 'team.csv', { type:'text/csv' })
    await userEvent.upload(screen.getByLabelText('Upload CSV file'), file)
    expect(onUpload).toHaveBeenCalledWith(file)
    await userEvent.click(screen.getByRole('button', { name:/Load sample dataset/ }))
    expect(onDemo).toHaveBeenCalledOnce()
  })
  it('rejects an unsupported dropped file without calling the API', async () => {
    const onUpload = vi.fn()
    render(<UploadZone onUpload={onUpload} onDemo={vi.fn()} busy={false} />)
    const file = new File(['{}'], 'team.json', { type:'application/json' })
    fireEvent.drop(screen.getByText('Drop your dataset here').parentElement!, { dataTransfer:{ files:[file] } })
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Please choose a CSV file'))
    expect(onUpload).not.toHaveBeenCalled()
  })
  it('disables choosing files during an upload', () => {
    render(<UploadZone onUpload={vi.fn()} onDemo={vi.fn()} busy />)
    expect(screen.getByRole('button', { name:/Choose a file/ })).toBeDisabled()
    expect(screen.getByText('Getting your data ready…')).toBeInTheDocument()
  })
})
