import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { ApiError } from '../../api/client'
import {
  approveRepair,
  rejectRepair,
  repairPipeline,
  resumePipeline,
  retestPipeline,
  skipRepair,
  skipRetest,
  startPipeline,
} from '../../api/pipeline'
import { PIPELINE_GATES } from '../../api/types'
import { installMswServer } from '../mocks/install'
import { server } from '../mocks/server'

installMswServer()

describe('pipeline mutations', () => {
  it('start returns the authoritative running state', async () => {
    const state = await startPipeline('demo_project')
    expect(state.overall_status).toBe('running')
    expect(state.current_stage).toBe('profile')
    expect(state.available_actions).toEqual([])
  })

  it('resume returns the authoritative running state', async () => {
    const state = await resumePipeline('demo_project')
    expect(state.overall_status).toBe('running')
    expect(state.current_stage).toBe('generate')
  })

  it('retest advances to the awaiting_repair_decision gate', async () => {
    const state = await retestPipeline('demo_project')
    expect(state.overall_status).toBe('waiting_for_user')
    expect(state.current_stage).toBe(PIPELINE_GATES.REPAIR)
    expect(state.available_actions).toEqual(['repair', 'skip_repair'])
  })

  it('skip-retest advances to the awaiting_repair_decision gate', async () => {
    const state = await skipRetest('demo_project')
    expect(state.current_stage).toBe(PIPELINE_GATES.REPAIR)
    expect(state.available_actions).toEqual(['repair', 'skip_repair'])
  })

  it('repair advances to the awaiting_repair_approval gate', async () => {
    const state = await repairPipeline('demo_project')
    expect(state.overall_status).toBe('waiting_for_approval')
    expect(state.current_stage).toBe(PIPELINE_GATES.APPROVAL)
    expect(state.available_actions).toEqual(['approve', 'reject'])
  })

  it('skip-repair completes the pipeline', async () => {
    const state = await skipRepair('demo_project')
    expect(state.overall_status).toBe('completed')
    expect(state.available_actions).toEqual([])
  })

  it('approve completes the pipeline', async () => {
    const state = await approveRepair('demo_project')
    expect(state.overall_status).toBe('completed')
  })

  it('reject records the rejection', async () => {
    const state = await rejectRepair('demo_project')
    expect(state.overall_status).toBe('rejected')
  })
})

describe('pipeline mutation error handling', () => {
  it('preserves HTTP 409 as a distinguishable conflict', async () => {
    const error = await startPipeline('conflict').then(
      () => null,
      (err: unknown) => err,
    )

    expect(error).toBeInstanceOf(ApiError)
    if (error instanceof ApiError) {
      expect(error.status).toBe(409)
      expect(error.isConflict()).toBe(true)
      expect(error.message).toMatch(/^Invalid pipeline gate/)
    }
  })

  it('rejects malformed success bodies as ApiError with the status preserved', async () => {
    const error = await startPipeline('malformed').then(
      () => null,
      (err: unknown) => err,
    )

    expect(error).toBeInstanceOf(ApiError)
    if (error instanceof ApiError) {
      expect(error.status).toBe(200)
      expect(error.message).toMatch(/Unexpected response format/)
    }
  })

  it('rejects an unknown pipeline action with 404, not a fabricated success', async () => {
    const res = await fetch(
      '/api/projects/demo_project/pipeline/not_a_real_action',
      { method: 'POST' },
    )
    expect(res.status).toBe(404)
    const body = (await res.json()) as { detail?: unknown }
    expect(body.detail).toMatch(/Unknown pipeline action/)
  })

  it('rejects a gate-invalid action with HTTP 409 instead of fabricating a state', async () => {
    const error = await approveRepair('demo_project').then(
      () => null,
      (err: unknown) => err,
    )
    expect(error).toBeInstanceOf(ApiError)
    if (error instanceof ApiError) {
      expect(error.status).toBe(409)
      expect(error.isConflict()).toBe(true)
      expect(error.message).toMatch(/not permitted/)
    }
  })

  it('rejects retest when it is not in the project gated actions with 409', async () => {
    server.use(
      http.post('/api/projects/:projectId/pipeline/:action', () =>
        HttpResponse.json({ detail: 'Invalid pipeline gate: action retest not permitted' }, {
          status: 409,
        }),
      ),
    )
    const error = await retestPipeline('demo_project').then(
      () => null,
      (err: unknown) => err,
    )
    expect(error).toBeInstanceOf(ApiError)
    if (error instanceof ApiError) {
      expect(error.status).toBe(409)
    }
  })

  it('wraps network failures as ApiError with null status', async () => {
    server.use(
      http.post('/api/projects/net_bad/pipeline/start', () =>
        HttpResponse.error(),
      ),
    )

    const error = await startPipeline('net_bad').then(
      () => null,
      (err: unknown) => err,
    )

    expect(error).toBeInstanceOf(ApiError)
    if (error instanceof ApiError) {
      expect(error.status).toBeNull()
    }
  })
})