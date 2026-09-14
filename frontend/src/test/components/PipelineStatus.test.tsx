import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PipelineStatus } from '../../components/PipelineStatus'
import { pipelineFixture } from '../mocks/handlers'

function renderStatus(status: Parameters<typeof pipelineFixture>[0]) {
  return render(<PipelineStatus state={pipelineFixture(status)} />)
}

describe('PipelineStatus', () => {
  it('renders overall status with its raw seed value', () => {
    renderStatus('running')
    expect(screen.getByText('(running)')).toBeDefined()
    expect(screen.getByText('Stage: Profile')).toBeDefined()
  })

  it('renders the current stage verb and raw value', () => {
    renderStatus('waiting_for_user')
    expect(screen.getByText('(awaiting_retest_decision)')).toBeDefined()
  })

  it('renders the improvement round when present', () => {
    renderStatus('waiting_for_user')
    expect(screen.getByText('Improvement round 3 of 3')).toBeDefined()
  })

  it('reports a required user decision without rendering action buttons', () => {
    renderStatus('waiting_for_user')
    expect(
      screen.getByText(/A user decision is required/i),
    ).toBeDefined()
    expect(
      screen.getByText(/Possible actions: retest, skip_retest/),
    ).toBeDefined()
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  it('reports approval as a waiting-for-approval state', () => {
    renderStatus('waiting_for_approval')
    expect(screen.getByText('(waiting_for_approval)')).toBeDefined()
    expect(screen.getByText('(awaiting_repair_approval)')).toBeDefined()
  })

  it('renders reason detail', () => {
    renderStatus('completed')
    expect(screen.getByText('Pipeline completed successfully.')).toBeDefined()
  })

  it('renders warnings distinctly from fatal errors', () => {
    renderStatus('blocked')
    expect(screen.getAllByText('Docker runtime unavailable.')).toBeDefined()
    expect(screen.queryByText(/Error/)).toBeNull()
  })

  it('renders the fatal error section when populated', () => {
    const state = pipelineFixture('failed', { error: 'Unhandled crash.' })
    render(<PipelineStatus state={state} />)
    expect(screen.getByText('Unhandled crash.')).toBeDefined()
  })

  it('omits absence of reason/warnings/error', () => {
    renderStatus('running')
    expect(screen.queryByText('Reason')).toBeNull()
    expect(screen.queryByText('Warnings')).toBeNull()
  })
})