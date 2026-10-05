import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import StatisticsPanel from './StatisticsPanel'

describe('StatisticsPanel', () => {
  it('shows recommendations and expands numeric descriptive statistics', async () => {
    render(<StatisticsPanel statistics={{ duplicate_rows:3, warnings:[{code:'duplicates',message:'3 duplicate rows found.'}], columns:[{ name:'age',type:'numeric',missing:3,unique:45,count:120,mean:37.5,median:36,std:10,min:18,max:65,q1:29,q3:43,outlier_count:1 }] }} />)
    expect(screen.getByText('3 duplicate rows found.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name:/age/ }))
    expect(screen.getByText('37.5')).toBeInTheDocument()
    expect(screen.getByText('Std. deviation')).toBeInTheDocument()
    expect(screen.getByText('25th percentile')).toBeInTheDocument()
  })
})
