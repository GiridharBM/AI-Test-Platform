import { cleanup, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { ErrorPanel } from '../../components/ErrorPanel'
import { pipelineFixture } from '../mocks/handlers'

beforeEach(() => {
  cleanup()
})

describe('ErrorPanel', () => {
  it('renders nothing for a non-terminal status', () => {
    render(
      <ErrorPanel state={pipelineFixture('running')} />,
    )
    expect(screen.queryByText('Failed')).toBeNull()
    expect(screen.queryByText('Blocked')).toBeNull()
  })

  it('renders nothing for completed status', () => {
    render(
      <ErrorPanel state={pipelineFixture('completed')} />,
    )
    expect(screen.queryByText('Completed')).toBeNull()
  })

  it('renders the failed status heading with raw chip', () => {
    render(
      <ErrorPanel state={pipelineFixture('failed')} />,
    )
    expect(screen.getByText('Failed')).toBeDefined()
    expect(screen.getByText('(failed)')).toBeDefined()
  })

  it('renders the bare reason without a prefix', () => {
    render(
      <ErrorPanel state={pipelineFixture('failed')} />,
    )
    expect(
      screen.getByText('Test execution failed: 3 of 2 tests failed.'),
    ).toBeDefined()
    expect(screen.queryByText(/^Reason:/)).toBeNull()
  })

  it('renders the blocked heading with raw chip', () => {
    render(
      <ErrorPanel state={pipelineFixture('blocked')} />,
    )
    expect(screen.getByText('Blocked')).toBeDefined()
    expect(screen.getByText('(blocked)')).toBeDefined()
  })

  it('renders warnings from the pipeline state', () => {
    render(
      <ErrorPanel state={pipelineFixture('blocked')} />,
    )
    expect(screen.getByText('Docker runtime unavailable.')).toBeDefined()
  })

  it('does not render the literal text Error', () => {
    render(
      <ErrorPanel state={pipelineFixture('blocked')} />,
    )
    expect(screen.queryByText('Error')).toBeNull()
  })

  it('renders the unavailable heading and reason', () => {
    render(
      <ErrorPanel state={pipelineFixture('unavailable')} />,
    )
    expect(screen.getByText('Unavailable')).toBeDefined()
    expect(screen.getByText('(unavailable)')).toBeDefined()
    expect(
      screen.getByText('Model provider API is unreachable.'),
    ).toBeDefined()
  })

  it('renders the rejected heading and raw chip', () => {
    render(
      <ErrorPanel state={pipelineFixture('rejected')} />,
    )
    expect(screen.getByText('Rejected')).toBeDefined()
    expect(screen.getByText('(rejected)')).toBeDefined()
  })

  it('renders the fatal error section when error is non-empty', () => {
    render(
      <ErrorPanel
        state={pipelineFixture('failed', { error: 'Process exited with code 1' })}
      />,
    )
    expect(screen.getByText('Fatal error')).toBeDefined()
    expect(screen.getByText('Process exited with code 1')).toBeDefined()
  })

  it('does not render fatal error when error is empty', () => {
    render(
      <ErrorPanel state={pipelineFixture('failed', { error: '' })} />,
    )
    expect(screen.queryByText('Fatal error')).toBeNull()
  })

  it('renders the rejected reason from StageHistory without duplication', () => {
    render(
      <ErrorPanel state={pipelineFixture('rejected')} />,
    )
    expect(
      screen.getByText('User rejected the repair candidate.'),
    ).toBeDefined()
    expect(screen.queryByText('Reason: User rejected the repair candidate.')).toBeNull()
  })
})
