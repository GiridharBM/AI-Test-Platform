import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import { pipelineKeys } from '../../api/pipeline'
import type { PipelineState } from '../../api/types'
import { PipelineActions } from '../../components/PipelineActions'
import { pipelineFixture } from '../mocks/handlers'
import { installMswServer } from '../mocks/install'
import { server } from '../mocks/server'

installMswServer()

const STATES: Record<string, PipelineState> = {
  waiting_for_user: pipelineFixture('waiting_for_user'),
  waiting_for_approval: pipelineFixture('waiting_for_approval'),
  completed: pipelineFixture('completed'),
}

function renderActions(status: keyof typeof STATES, projectId = 'p_waiting_user') {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
    },
  })
  render(
    <QueryClientProvider client={client}>
      <PipelineActions projectId={projectId} state={STATES[status]} />
    </QueryClientProvider>,
  )
  return client
}

beforeEach(() => {
  cleanup()
})

describe('PipelineActions', () => {
  it('renders the re-test gate buttons', () => {
    renderActions('waiting_for_user')
    expect(
      screen.getByRole('button', { name: 'Run re-test' }),
    ).toBeDefined()
    expect(
      screen.getByRole('button', { name: 'Skip re-test' }),
    ).toBeDefined()
  })

  it('renders the approval gate buttons', () => {
    renderActions('waiting_for_approval')
    expect(
      screen.getByRole('button', { name: 'Approve and apply repair' }),
    ).toBeDefined()
    expect(
      screen.getByRole('button', { name: 'Reject repair' }),
    ).toBeDefined()
  })

  it('renders nothing when no decision is required', () => {
    renderActions('completed')
    expect(screen.queryByText('Decision required')).toBeNull()
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  it('posts the action and caches the returned pipeline state', async () => {
    const client = renderActions('waiting_for_user')
    fireEvent.click(screen.getByRole('button', { name: 'Run re-test' }))
    await waitFor(() => {
      const cached = client.getQueryData<PipelineState>(
        pipelineKeys.detail('p_waiting_user'),
      )
      expect(cached?.current_stage).toBe('awaiting_repair_decision')
      expect(cached?.available_actions).toEqual(['repair', 'skip_repair'])
    })
  })

  it('disables the buttons while an action is in flight', async () => {
    let pendingResolve!: (value: Response) => void
    server.use(
      http.post('/api/projects/:projectId/pipeline/:action', () =>
        new Promise<Response>((resolve) => {
          pendingResolve = resolve
        }),
      ),
    )
    renderActions('waiting_for_user')
    fireEvent.click(screen.getByRole('button', { name: 'Run re-test' }))
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Run re-test' } as never),
      ).toBeDisabled()
      expect(
        screen.getByRole('button', { name: 'Skip re-test' }),
      ).toBeDisabled()
    })
    expect(screen.getByText('Working…')).toBeDefined()

    pendingResolve(
      HttpResponse.json(
        pipelineFixture('waiting_for_approval', {
          project_id: 'p_waiting_user',
          pipeline_id: 'p_waiting_user',
          current_stage: 'awaiting_repair_approval',
          user_decision_required: true,
          available_actions: ['approve', 'reject'],
        }),
      ),
    )
    await waitFor(() => {
      expect(screen.queryByText('Working…')).toBeNull()
    })
  })

  it('surfaces the backend 409 detail when the action is not permitted', async () => {
    renderActions(
      'waiting_for_user',
      'conflict',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Run re-test' }))
    expect(await screen.findByRole('alert')).toBeDefined()
    expect(
      await screen.findByText(/Invalid pipeline gate/i),
    ).toBeDefined()
  })

  it('surfaces a network error message', async () => {
    server.use(
      http.post('/api/projects/:projectId/pipeline/:action', () =>
        HttpResponse.error(),
      ),
    )
    renderActions('waiting_for_user')
    fireEvent.click(screen.getByRole('button', { name: 'Run re-test' }))
    expect(
      await screen.findByText(/Could not reach the server/i),
    ).toBeDefined()
  })
})