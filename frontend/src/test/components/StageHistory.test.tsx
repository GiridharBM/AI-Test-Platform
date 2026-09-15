import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StageHistory } from '../../components/StageHistory'
import type { StageRecord } from '../../api/types'

const records: StageRecord[] = [
  {
    stage: 'profile',
    status: 'success',
    start_time: '2026-01-01T09:00:00Z',
    end_time: '2026-01-01T09:00:01Z',
    result_id: 'profile-1',
    reason: '',
    warnings: [],
  },
  {
    stage: 'approve',
    status: 'rejected',
    start_time: '2026-01-01T09:30:00Z',
    end_time: '2026-01-01T09:30:00Z',
    result_id: '',
    reason: 'User rejected the repair candidate.',
    warnings: [],
  },
  {
    stage: 'execute',
    status: 'skipped',
    start_time: '2026-01-01T09:05:00Z',
    end_time: '2026-01-01T09:05:02Z',
    result_id: '',
    reason: '',
    warnings: ['No tests selected.'],
  },
]

describe('StageHistory', () => {
  it('shows a clean empty state when no history is recorded', () => {
    render(<StageHistory records={[]} />)
    expect(
      screen.getByText('No stage history recorded yet.'),
    ).toBeDefined()
  })

  it('renders each record with stage, status, and times', () => {
    render(<StageHistory records={records} />)
    expect(screen.getByText('(profile)')).toBeDefined()
    expect(screen.getAllByText('Success')).toHaveLength(1)
    expect(screen.getAllByText(/Started/).length).toBeGreaterThan(0)
  })

  it('shows reason and warnings for a record when present', () => {
    render(<StageHistory records={records} />)
    expect(
      screen.getByText('Reason: User rejected the repair candidate.'),
    ).toBeDefined()
    expect(screen.getByText('No tests selected.')).toBeDefined()
  })

  it('keeps records in chronological order', () => {
    render(<StageHistory records={records} />)
    const items = screen.getAllByRole('listitem').map((li) => li.textContent)
    const profileIndex = items.findIndex((t) => t?.includes('profile-1'))
    const executeIndex = items.findIndex((t) => t?.includes('No tests selected.'))
    expect(profileIndex).toBeLessThan(executeIndex)
  })

  it('labels a rejected approval record without claiming success', () => {
    render(<StageHistory records={records} />)
    expect(screen.getByText('Rejected')).toBeDefined()
    expect(screen.getByText('(approve)')).toBeDefined()
  })

  it('shows the result_id when present', () => {
    render(<StageHistory records={records} />)
    expect(screen.getByText('Result: profile-1')).toBeDefined()
  })

  it('does not show a Result line when result_id is empty', () => {
    render(<StageHistory records={records} />)
    const approveRecord = records[1]
    expect(approveRecord.result_id).toBe('')
    expect(screen.queryByText('Result: ')).toBeNull()
  })
})