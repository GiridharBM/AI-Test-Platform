import { act, renderHook, waitFor } from '@testing-library/react'
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
  usePipelineAction,
} from '../../hooks/usePipeline'
import { useResultsDigest } from '../../hooks/useResultsDigest'
import { pipelineFixture, resultsDigestFixture } from '../mocks/handlers'
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

  it('invalidates the results digest when the pipeline state changes', async () => {
    let pipelineStatus: PipelineOverallStatus = 'running'
    let digestCalls = 0
    server.use(
      http.get('/api/projects/refresh_probe/pipeline', () =>
        HttpResponse.json(
          pipelineFixture(pipelineStatus, { project_id: 'refresh_probe' }),
        ),
      ),
      http.get('/api/projects/refresh_probe/results', () => {
        digestCalls += 1
        return HttpResponse.json(
          resultsDigestFixture({ project_id: 'refresh_probe' }),
        )
      }),
    )

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    function wrapper({ children }: PropsWithChildren) {
      return <QueryClientProvider client={client}>{children}</QueryClientProvider>
    }

    renderHook(() => useResultsDigest('refresh_probe'), { wrapper })
    const { result } = renderHook(() => usePipeline('refresh_probe'), { wrapper })

    await waitFor(() =>
      expect(result.current.data?.overall_status).toBe('running'),
    )
    expect(digestCalls).toBe(1)

    await act(async () => {
      await result.current.refetch()
    })
    expect(digestCalls).toBe(1)

    pipelineStatus = 'completed'
    await act(async () => {
      await result.current.refetch()
    })
    await waitFor(() => expect(digestCalls).toBe(2))
  })

  it('does not invalidate the results digest when a poll returns the same state', async () => {
    let digestCalls = 0
    server.use(
      http.get('/api/projects/idle_probe/pipeline', () =>
        HttpResponse.json(
          pipelineFixture('running', { project_id: 'idle_probe' }),
        ),
      ),
      http.get('/api/projects/idle_probe/results', () => {
        digestCalls += 1
        return HttpResponse.json(
          resultsDigestFixture({ project_id: 'idle_probe' }),
        )
      }),
    )

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    function wrapper({ children }: PropsWithChildren) {
      return <QueryClientProvider client={client}>{children}</QueryClientProvider>
    }

    renderHook(() => useResultsDigest('idle_probe'), { wrapper })
    const { result } = renderHook(() => usePipeline('idle_probe'), { wrapper })

    await waitFor(() =>
      expect(result.current.data?.overall_status).toBe('running'),
    )
    expect(digestCalls).toBe(1)

    await act(async () => {
      await result.current.refetch()
    })
    await act(async () => {
      await result.current.refetch()
    })
    expect(digestCalls).toBe(1)
  })
})

describe('usePipelineAction results freshness', () => {
  it('invalidates the results digest after a successful action', async () => {
    let digestCalls = 0
    server.use(
      http.get('/api/projects/action_refresh/results', () => {
        digestCalls += 1
        return HttpResponse.json(
          resultsDigestFixture({ project_id: 'action_refresh' }),
        )
      }),
    )

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    function wrapper({ children }: PropsWithChildren) {
      return <QueryClientProvider client={client}>{children}</QueryClientProvider>
    }

    renderHook(() => useResultsDigest('action_refresh'), { wrapper })
    const { result } = renderHook(() => usePipelineAction('action_refresh'), {
      wrapper,
    })

    await act(async () => {
      result.current.mutate('approve')
    })
    await act(async () => {
      await Promise.resolve()
    })
    await waitFor(() => expect(digestCalls).toBe(2))
  })
})