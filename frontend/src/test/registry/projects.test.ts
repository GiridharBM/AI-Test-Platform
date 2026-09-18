import { beforeEach, describe, expect, it } from 'vitest'

import {
  clearLocalProjects,
  getLocalProjects,
  readLocalProjects,
  registerLocalProject,
  removeLocalProject,
} from '../../registry/projects'

const STORAGE_KEY = 'auto-testing.projects'

beforeEach(() => {
  window.localStorage.clear()
})

describe('local project registry', () => {
  it('loads an empty registry when nothing is stored', () => {
    expect(getLocalProjects()).toEqual([])
  })

  it('loads a valid stored registry', () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        { id: 'aaa', name: 'Alpha' },
        { id: 'bbb', name: 'Beta', createdAt: '2026-01-01T00:00:00Z' },
      ]),
    )
    expect(getLocalProjects().map((p) => p.id)).toEqual(['aaa', 'bbb'])
    expect(getLocalProjects()[1].name).toBe('Beta')
  })

  it('falls back to an empty registry on corrupt JSON and removes the value', () => {
    window.localStorage.setItem(STORAGE_KEY, 'not json {{{')
    expect(getLocalProjects()).toEqual([])
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('falls back to an empty registry when the value is not an array', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ id: 'x' }))
    expect(getLocalProjects()).toEqual([])
  })

  it('drops invalid and duplicate entries from a partial registry', () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        { id: 'aaa', name: 'Alpha' },
        { id: 42, name: 'NotAnId' },
        { name: 'NoId' },
        'garbage',
        { id: 'aaa', name: 'Alpha-dup' },
      ]),
    )
    expect(getLocalProjects()).toEqual([{ id: 'aaa', name: 'Alpha' }])
  })

  it('persists a registered project', () => {
    const result = registerLocalProject({ id: 'p1', name: 'Proj' })
    expect(result).toEqual([{ id: 'p1', name: 'Proj' }])
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '[]')).toEqual(
      [{ id: 'p1', name: 'Proj' }],
    )
  })

  it('replaces an existing entry instead of duplicating the same id', () => {
    registerLocalProject({ id: 'p1', name: 'Old' })
    registerLocalProject({ id: 'p1', name: 'New', createdAt: '2026-02-01' })
    registerLocalProject({ id: 'p2', name: 'Other' })

    const list = getLocalProjects()
    expect(list.filter((p) => p.id === 'p1')).toHaveLength(1)
    expect(list.find((p) => p.id === 'p1')).toEqual({
      id: 'p1',
      name: 'New',
      createdAt: '2026-02-01',
    })
  })

  it('clears the registry', () => {
    registerLocalProject({ id: 'p1', name: 'Proj' })
    expect(clearLocalProjects()).toEqual([])
    expect(getLocalProjects()).toEqual([])
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('reports no recovery for a clean registry', () => {
    registerLocalProject({ id: 'p1', name: 'Proj' })
    expect(readLocalProjects()).toEqual({
      projects: [{ id: 'p1', name: 'Proj' }],
      recovered: false,
    })
  })

  it('reports recovery when corrupt JSON is repaired', () => {
    window.localStorage.setItem(STORAGE_KEY, 'not json {{{')
    expect(readLocalProjects()).toEqual({ projects: [], recovered: true })
  })

  it('reports recovery when invalid entries are skipped but keeps valid ones', () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        { id: 'aaa', name: 'Alpha' },
        'garbage',
        { id: 'bbb', name: 'Beta' },
        { id: 'bbb', name: 'Beta-dup' },
      ]),
    )
    expect(readLocalProjects()).toEqual({
      projects: [
        { id: 'aaa', name: 'Alpha' },
        { id: 'bbb', name: 'Beta' },
      ],
      recovered: true,
    })
  })

  it('removes a single project without touching the others', () => {
    registerLocalProject({ id: 'p1', name: 'One' })
    registerLocalProject({ id: 'p2', name: 'Two' })
    const result = removeLocalProject('p1')
    expect(result.map((p) => p.id)).toEqual(['p2'])
    expect(getLocalProjects().map((p) => p.id)).toEqual(['p2'])
  })

  it('removing an unknown id leaves the registry unchanged', () => {
    registerLocalProject({ id: 'p1', name: 'One' })
    expect(removeLocalProject('nope').map((p) => p.id)).toEqual(['p1'])
  })

  it('accepts an old-format entry with only id and name', () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([{ id: 'aaa', name: 'Alpha' }]),
    )
    expect(readLocalProjects()).toEqual({
      projects: [{ id: 'aaa', name: 'Alpha' }],
      recovered: false,
    })
  })

  it('accepts a new-format entry with full metadata', () => {
    registerLocalProject({
      id: 'p1',
      name: 'Proj',
      createdAt: '2026-01-01T00:00:00Z',
      origin: 'upload',
      fileCount: 12,
      profiled: true,
    })
    expect(getLocalProjects()).toEqual([
      {
        id: 'p1',
        name: 'Proj',
        createdAt: '2026-01-01T00:00:00Z',
        origin: 'upload',
        fileCount: 12,
        profiled: true,
      },
    ])
  })

  it('accepts a mix of old and new entries', () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        { id: 'old', name: 'Old' },
        {
          id: 'new',
          name: 'New',
          origin: 'path',
          fileCount: 0,
          profiled: false,
        },
      ]),
    )
    expect(getLocalProjects()).toEqual([
      { id: 'old', name: 'Old' },
      { id: 'new', name: 'New', origin: 'path', fileCount: 0, profiled: false },
    ])
  })

  it('drops malformed optional metadata but keeps the entry', () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        {
          id: 'p1',
          name: 'Proj',
          origin: 'sneaky',
          fileCount: -5,
          profiled: 'yes',
        },
      ]),
    )
    expect(getLocalProjects()).toEqual([{ id: 'p1', name: 'Proj' }])
  })

  it('treats a null file count as missing metadata', () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([{ id: 'p1', name: 'Proj', fileCount: null }]),
    )
    expect(getLocalProjects()).toEqual([{ id: 'p1', name: 'Proj' }])
  })

  it('preserves metadata through register and re-register of the same id', () => {
    registerLocalProject({ id: 'p1', name: 'Old', origin: 'upload' })
    registerLocalProject({
      id: 'p1',
      name: 'New',
      fileCount: 3,
      profiled: true,
    })
    expect(getLocalProjects()).toEqual([
      { id: 'p1', name: 'New', fileCount: 3, profiled: true },
    ])
  })
})