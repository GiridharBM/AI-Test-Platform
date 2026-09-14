import { describe, expect, it } from 'vitest'

import { ApiError } from '../../api/client'
import { getPipeline } from '../../api/projects'
import { PIPELINE_GATES } from '../../api/types'
import { installMswServer } from '../mocks/install'

installMswServer()

describe('getPipeline', () => {
  it('returns the authoritative pipeline state on success', async () => {
    const state = await getPipeline('demo_project')

    expect(state.project_id).toBe('demo_project')
    expect(state.overall_status).toBe('waiting_for_user')
    expect(state.user_decision_required).toBe(true)
    expect(state.current_stage).toBe(PIPELINE_GATES.RETEST)
    expect(state.available_actions).toEqual(['retest', 'skip_retest'])
    expect(state.stage_history[0].status).toBe('success')
    expect(state.warnings).toEqual([])
  })

  it('rejects with ApiError status 404 when no pipeline exists', async () => {
    const error = await getPipeline('no_pipeline').then(
      () => null,
      (err: unknown) => err,
    )

    expect(error).toBeInstanceOf(ApiError)
    if (error instanceof ApiError) {
      expect(error.status).toBe(404)
      expect(error.message).toBe('No pipeline state for this project.')
      expect(error.detail).toEqual({
        detail: 'No pipeline state for this project.',
      })
    }
  })
})