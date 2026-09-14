import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PropsWithChildren } from 'react'

import type { PipelineOverallStatus, PipelineState } from '../../api/types'
import {
  PIPELINE_POLL_RUNNING_MS,
  PIPELINE_POLL_WAITING_MS,
  pipelinePollingIntervalMs,
  usePipeline,
} from '../../hooks/usePipeline'
import { pipelineFixture } from '../mocks/handlers'
import { installMswServer } from '../mocks/install'
import { server } from '../mocks/server'

installMswServer()

afterEach(() => {
  vi.useRealTimers()
})

const TERMINAL: PipelineOverallStatus[] = [
  'completed',
  'failed',
  'blocked',
  'unavailable',
  'rejected',
]

function stateWithStatus(overall_status: PipelineOverallStatus): PipelineState {
  return { overall_status } as PipelineState
}

describe('pipelinePollingIntervalMs', () => {
  it('uses 2000ms while the pipeline is running', () => {
    expect(pipelinePollingIntervalMs(stateWithStatus('running'))).toBe(
      PIPELINE_POLL_RUNNING_MS,
    )
  })

  it('uses 4000ms while waiting for the user', () => {
    expect(pipelinePollingIntervalMs(stateWithStatus('waiting_for_user'))).toBe(
      PIPELINE_POLL_WAITING_MS,
    )
  })

  it('uses 4000ms while waiting for approval', () => {
    expect(
      pipelinePollingIntervalMs(stateWithStatus('waiting_for_approval')),
    ).toBe(PIPELINE_POLL_WAITING_MS)
  })

  it('stops polling at every terminal status', () => {
    for (const status of TERMINAL) {
      expect(pipelinePollingIntervalMs(stateWithStatus(status))).toBe(false)
    }
  })

  it('does not schedule polling without authoritative data', () => {
    expect(pipelinePollingIntervalMs(undefined)).toBe(false)
  })
})

describe('usePipeline polling', () => {
  function wrapper({ children }: PropsWithChildren) {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }

  it('refetches on the running interval and stops after a terminal state', async () => {
    vi.useFakeTimers()
    let fetchCount = 0
    server.use(
      http.get('/api/projects/poll_running/pipeline', () => {
        fetchCount += 1
        return HttpResponse.json(
          pipelineFixture(fetchCount >= 2 ? 'completed' : 'running', {
            project_id: 'poll_running',
          }),
        )
      }),
    )

    const { result } = renderHook(() => usePipeline('poll_running'), {
      wrapper,
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(fetchCount).toBe(1)
    expect(result.current.data?.overall_status).toBe('running')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(PIPELINE_POLL_RUNNING_MS + 1)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(fetchCount).toBe(2)
    expect(result.current.data?.overall_status).toBe('completed')

    const countAtTerminal = fetchCount

    await act(async () => {
      await vi.advanceTimersByTimeAsync(PIPELINE_POLL_RUNNING_MS * 6)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(fetchCount).toBe(countAtTerminal)
  })
})