import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { DecisionCard } from '../../components/DecisionCard'
import { pipelineFixture } from '../mocks/handlers'
import { installMswServer } from '../mocks/install'

installMswServer()

beforeEach(() => {
  cleanup()
})

function renderDecisionCard(
  overrides: Record<string, unknown> = {},
  projectId = 'test_project',
) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
    },
  })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/']}>
        <DecisionCard
          projectId={projectId}
          state={pipelineFixture('waiting_for_user', overrides) as never}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DecisionCard', () => {
  it('renders nothing when user_decision_required is false', () => {
    renderDecisionCard({ user_decision_required: false })
    expect(screen.queryByText('Decision required')).toBeNull()
  })

  it('renders the decision required heading when decision is needed', () => {
    renderDecisionCard()
    expect(screen.getByText('Decision required')).toBeDefined()
  })

  it('shows the current stage label in the gate message', () => {
    renderDecisionCard({ current_stage: 'awaiting_retest_decision' })
    expect(
      screen.getByText(/Awaiting retest decision/),
    ).toBeDefined()
  })

  it('renders the reason when present', () => {
    renderDecisionCard({
      reason: 'Improvements did not resolve the diagnosed failures.',
    })
    expect(
      screen.getByText('Reason: Improvements did not resolve the diagnosed failures.'),
    ).toBeDefined()
  })

  it('does not render the reason when empty', () => {
    renderDecisionCard({ reason: '' })
    expect(screen.queryByText(/^Reason:/)).toBeNull()
  })

  it('renders the action buttons via PipelineActions', () => {
    renderDecisionCard()
    expect(
      screen.getByRole('button', { name: 'Run re-test' }),
    ).toBeDefined()
    expect(
      screen.getByRole('button', { name: 'Skip re-test' }),
    ).toBeDefined()
  })

  it('renders approval buttons at the approval gate', () => {
    renderDecisionCard({
      current_stage: 'awaiting_repair_approval',
      overall_status: 'waiting_for_approval',
      available_actions: ['approve', 'reject'],
    })
    expect(
      screen.getByRole('button', { name: 'Approve and apply repair' }),
    ).toBeDefined()
    expect(
      screen.getByRole('button', { name: 'Reject repair' }),
    ).toBeDefined()
  })
})
