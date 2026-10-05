import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import DatasetTable from './DatasetTable'
import { dataset } from '../test-fixtures'

describe('DatasetTable', () => {
  it('displays typed columns, missing cells, and server pagination', async () => {
    const onPage = vi.fn()
    render(<DatasetTable metadata={dataset} preview={{ columns:['name','age','salary'],rows:[{ name:'Ada',age:null,salary:65000 }],total:123,page:1,page_size:50 }} loading={false} page={1} onPage={onPage} />)
    expect(screen.getByText('Ada')).toBeInTheDocument()
    expect(screen.getByText('—')).toHaveClass('missing-cell')
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name:'Previous page' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name:'Next page' }))
    expect(onPage).toHaveBeenCalledWith(2)
  })
  it('prevents requesting pages beyond the last page', () => {
    render(<DatasetTable metadata={dataset} preview={null} loading={false} page={3} onPage={vi.fn()} />)
    expect(screen.getByRole('button', { name:'Next page' })).toBeDisabled()
  })
})
