import { describe, expect, it } from 'vitest'

import type { ProjectSummary } from '../../api/types'
import { mergeProjects, type LocalProject } from '../../registry/projects'

function remote(
  projectId: string,
  overrides: Partial<ProjectSummary> = {},
): ProjectSummary {
  return {
    project_id: projectId,
    name: `${projectId}-name`,
    origin: 'upload',
    file_count: null,
    created_at: '2026-01-01T00:00:00Z',
    profiled: false,
    ...overrides,
  }
}

function local(
  id: string,
  overrides: Partial<LocalProject> = {},
): LocalProject {
  return { id, name: `${id}-local`, ...overrides }
}

describe('mergeProjects', () => {
  it('returns an empty list when both sources are empty', () => {
    expect(mergeProjects([], [])).toEqual([])
  })

  it('preserves local-only projects untouched', () => {
    const localProjects = [local('only', { fileCount: 2 })]
    expect(mergeProjects(localProjects, [])).toEqual(localProjects)
  })

  it('maps backend-only projects to LocalProject shape in backend order', () => {
    const backend = [remote('p1'), remote('p2', { origin: 'path' })]
    expect(mergeProjects([], backend)).toEqual([
      {
        id: 'p1',
        name: 'p1-name',
        createdAt: '2026-01-01T00:00:00Z',
        origin: 'upload',
        fileCount: undefined,
        profiled: false,
      },
      {
        id: 'p2',
        name: 'p2-name',
        createdAt: '2026-01-01T00:00:00Z',
        origin: 'path',
        fileCount: undefined,
        profiled: false,
      },
    ])
  })

  it('lets backend metadata win but keeps the local list position', () => {
    const localProjects = [
      local('p1', { name: 'Stale Local Name', fileCount: 0, profiled: false }),
      local('p2'),
    ]
    const backend = [remote('p1', { name: 'Fresh Server Name', file_count: 7 })]
    const merged = mergeProjects(localProjects, backend)
    expect(merged).toHaveLength(2)
    expect(merged[0]).toEqual({
      id: 'p1',
      name: 'Fresh Server Name',
      createdAt: '2026-01-01T00:00:00Z',
      origin: 'upload',
      fileCount: 7,
      profiled: false,
    })
    expect(merged[1].id).toBe('p2')
  })

  it('appends backend-only projects after local ones, deduped by id', () => {
    const merged = mergeProjects(
      [local('p0'), local('p2')],
      [remote('p1'), remote('p2', { name: 'tagged' }), remote('p3')],
    )
    expect(merged.map((p) => p.id)).toEqual(['p0', 'p2', 'p1', 'p3'])
    expect(merged[1].name).toBe('tagged')
  })

  it('maps a null file_count to undefined fileCount', () => {
    const merged = mergeProjects([], [remote('p1', { file_count: null })])
    expect(merged[0].fileCount).toBeUndefined()
  })
})