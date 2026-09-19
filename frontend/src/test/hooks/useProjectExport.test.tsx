import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PropsWithChildren } from 'react'

import { useProjectExport } from '../../hooks/useProjectExport'
import { usePipeline } from '../../hooks/usePipeline'
import { pipelineFixture } from '../mocks/handlers'
import { installMswServer } from '../mocks/install'
import { server } from '../mocks/server'

installMswServer()

afterEach(() => {
  vi.restoreAllMocks()
  delete (URL as { createObjectURL?: unknown }).createObjectURL
  delete (URL as { revokeObjectURL?: unknown }).revokeObjectURL
})

function stubUrlMethods() {
  const createObjectURL = vi.fn().mockReturnValue('blob:fixture')
  const revokeObjectURL = vi.fn()
  Object.defineProperty(URL, 'createObjectURL', {
    writable: true,
    configurable: true,
    value: createObjectURL,
  })
  Object.defineProperty(URL, 'revokeObjectURL', {
    writable: true,
    configurable: true,
    value: revokeObjectURL,
  })
  return { createObjectURL, revokeObjectURL }
}

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('useProjectExport', () => {
  it('downloads the exported blob via a temporary anchor on success', async () => {
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})
    const { createObjectURL, revokeObjectURL } = stubUrlMethods()

    const { result } = renderHook(() => useProjectExport('demo_project'), {
      wrapper,
    })

    await act(async () => {
      await result.current.mutateAsync()
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(click).toHaveBeenCalledTimes(1)
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
    expect(revokeObjectURL).toHaveBeenCalledTimes(1)
  })

  it('refetches authoritative state when the export conflicts (409)', async () => {
    let pipelineFetches = 0
    server.use(
      http.get('/api/projects/running_export/pipeline', () => {
        pipelineFetches += 1
        return HttpResponse.json(
          pipelineFixture('completed', { project_id: 'running_export' }),
        )
      }),
    )
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const sharedWrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    )

    const { result: pipelineResult } = renderHook(
      () => usePipeline('running_export'),
      { wrapper: sharedWrapper },
    )
    const { result } = renderHook(() => useProjectExport('running_export'), {
      wrapper: sharedWrapper,
    })

    await waitFor(() => expect(pipelineResult.current.isSuccess).toBe(true))
    const before = pipelineFetches

    await act(async () => {
      await result.current.mutateAsync().catch(() => {})
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(click).not.toHaveBeenCalled()
    await waitFor(() => expect(pipelineFetches).toBeGreaterThan(before))
  })
})