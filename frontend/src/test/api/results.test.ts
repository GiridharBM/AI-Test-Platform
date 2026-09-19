import { describe, expect, it } from 'vitest'

import { ApiError } from '../../api/client'
import { getResults } from '../../api/results'
import { installMswServer } from '../mocks/install'

installMswServer()

describe('getResults', () => {
  it('returns the parsed digest on success', async () => {
    const digest = await getResults('r_complete')

    expect(digest.project_id).toBe('r_complete')
    expect(digest.overall_verdict).toBe('passed')
    expect(digest.test_counts?.passed).toBe(2)
    expect(digest.failing_tests).toEqual([])
  })

  it('rejects with ApiError status 404 for an unknown project', async () => {
    const error = await getResults('missing').then(
      () => null,
      (err: unknown) => err,
    )

    expect(error).toBeInstanceOf(ApiError)
    if (error instanceof ApiError) {
      expect(error.status).toBe(404)
    }
  })

  it('rejects when the response body is malformed JSON', async () => {
    const error = await getResults('malformed').then(
      () => null,
      (err: unknown) => err,
    )

    expect(error).toBeInstanceOf(ApiError)
    if (error instanceof ApiError) {
      expect(error.status).toBe(200)
    }
  })
})