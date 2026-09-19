import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PropsWithChildren } from 'react'

import { useResultsDigest } from '../../hooks/useResultsDigest'
import { installMswServer } from '../mocks/install'

installMswServer()

beforeEach(() => {
  vi.restoreAllMocks()
})

function wrapper({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('useResultsDigest', () => {
  it('fetches the digest for a project', async () => {
    const { result } = renderHook(() => useResultsDigest('r_complete'), {
      wrapper,
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.overall_verdict).toBe('passed')
    expect(result.current.data?.project_id).toBe('r_complete')
  })

  it('surfaces an error for an unknown project', async () => {
    const { result } = renderHook(() => useResultsDigest('missing'), {
      wrapper,
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})