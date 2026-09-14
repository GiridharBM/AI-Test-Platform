import { describe, expect, it } from 'vitest'

import { ApiError } from '../../api/client'
import { getProject } from '../../api/projects'
import { installMswServer } from '../mocks/install'

installMswServer()

describe('getProject', () => {
  it('returns project details on success', async () => {
    const project = await getProject('demo_project')

    expect(project.project_id).toBe('demo_project')
    expect(project.name).toBe('demo_project')
    expect(project.origin).toBe('upload')
    expect(project.profile).not.toBeNull()
    expect(project.retest?.status).toBe('still_failing')
    expect(project.repair?.selected_candidate?.candidate_id).toBe('c1')
    expect(project.evaluation?.coverage.line_percentage).toBe(66.7)
    expect(project.diagnosis?.overall_status).toBe('failures_diagnosed')
    expect(project.execution?.overall_status).toBe('failed')
  })

  it('rejects with ApiError status 404 when the project is missing', async () => {
    const error = await getProject('missing').then(
      () => null,
      (err: unknown) => err,
    )

    expect(error).toBeInstanceOf(ApiError)
    if (error instanceof ApiError) {
      expect(error.status).toBe(404)
      expect(error.isConflict()).toBe(false)
      expect(error.message).toBe('Project metadata not found')
    }
  })
})