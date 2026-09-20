import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it } from 'vitest'

import { pipelineKeys } from '../../api/pipeline'
import type { PipelineState } from '../../api/types'
import { ErrorPanel } from '../../components/ErrorPanel'
import { pipelineFixture } from '../mocks/handlers'
import { installMswServer } from '../mocks/install'

installMswServer()

function renderPanel(
  status: PipelineState['overall_status'],
  overrides: Partial<PipelineState> = {},
  projectId = 'demo_project',
) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
    },
  })
  render(
    <QueryClientProvider client={client}>
      <ErrorPanel projectId={projectId} state={pipelineFixture(status, overrides)} />
    </QueryClientProvider>,
  )
  return client
}

beforeEach(() => {
  cleanup()
})

describe('ErrorPanel', () => {
  it('renders nothing for a non-terminal status', () => {
    renderPanel('running')
    expect(screen.queryByText('Failed')).toBeNull()
    expect(screen.queryByText('Blocked')).toBeNull()
  })

  it('renders nothing for completed status', () => {
    renderPanel('completed')
    expect(screen.queryByText('Completed')).toBeNull()
  })

  it('renders the failed status heading with raw chip', () => {
    renderPanel('failed')
    expect(screen.getByText('Failed')).toBeDefined()
    expect(screen.getByText('(failed)')).toBeDefined()
  })

  it('renders the bare reason without a prefix', () => {
    renderPanel('failed')
    expect(
      screen.getByText('Test execution failed: 3 of 2 tests failed.'),
    ).toBeDefined()
    expect(screen.queryByText(/^Reason:/)).toBeNull()
  })

  it('renders the blocked heading with raw chip', () => {
    renderPanel('blocked')
    expect(screen.getByText('Blocked')).toBeDefined()
    expect(screen.getByText('(blocked)')).toBeDefined()
  })

  it('renders warnings from the pipeline state', () => {
    renderPanel('blocked')
    expect(screen.getByText('Docker runtime unavailable.')).toBeDefined()
  })

  it('does not render the literal text Error', () => {
    renderPanel('blocked')
    expect(screen.queryByText('Error')).toBeNull()
  })

  it('renders the unavailable heading and reason', () => {
    renderPanel('unavailable')
    expect(screen.getByText('Unavailable')).toBeDefined()
    expect(screen.getByText('(unavailable)')).toBeDefined()
    expect(
      screen.getByText('Model provider API is unreachable.'),
    ).toBeDefined()
  })

  it('renders the rejected heading and raw chip', () => {
    renderPanel('rejected')
    expect(screen.getByText('Rejected')).toBeDefined()
    expect(screen.getByText('(rejected)')).toBeDefined()
  })

  it('renders the fatal error section when error is non-empty', () => {
    renderPanel('failed', { error: 'Process exited with code 1' })
    expect(screen.getByText('Fatal error')).toBeDefined()
    expect(screen.getByText('Process exited with code 1')).toBeDefined()
  })

  it('does not render fatal error when error is empty', () => {
    renderPanel('failed', { error: '' })
    expect(screen.queryByText('Fatal error')).toBeNull()
  })

  it('renders the rejected reason from StageHistory without duplication', () => {
    renderPanel('rejected')
    expect(
      screen.getByText('User rejected the repair candidate.'),
    ).toBeDefined()
    expect(screen.queryByText('Reason: User rejected the repair candidate.')).toBeNull()
  })

  it('renders a resume button for failed status', () => {
    renderPanel('failed')
    expect(
      screen.getByRole('button', { name: 'Resume pipeline' }),
    ).toBeDefined()
  })

  it('renders a resume button for unavailable status', () => {
    renderPanel('unavailable')
    expect(
      screen.getByRole('button', { name: 'Resume pipeline' }),
    ).toBeDefined()
  })

  it('does not render a resume button for blocked or rejected statuses', () => {
    renderPanel('blocked')
    expect(
      screen.queryByRole('button', { name: 'Resume pipeline' }),
    ).toBeNull()
    renderPanel('rejected')
    expect(
      screen.queryByRole('button', { name: 'Resume pipeline' }),
    ).toBeNull()
  })

  it('posts the resume action and caches the returned running state', async () => {
    const client = renderPanel('failed')
    fireEvent.click(screen.getByRole('button', { name: 'Resume pipeline' }))
    await waitFor(() => {
      const cached = client.getQueryData<PipelineState>(
        pipelineKeys.detail('demo_project'),
      )
      expect(cached?.overall_status).toBe('running')
      expect(cached?.current_stage).toBe('generate')
    })
  })

  it('surfaces an error when the resume action fails', async () => {
    const { HttpResponse, http } = await import('msw')
    const { server } = await import('../mocks/server')
    server.use(
      http.post('/api/projects/demo_project/pipeline/resume', () =>
        HttpResponse.error(),
      ),
    )
    renderPanel('failed')
    fireEvent.click(screen.getByRole('button', { name: 'Resume pipeline' }))
    expect(
      await screen.findByText(/Could not reach the server/i),
    ).toBeDefined()
  })
})