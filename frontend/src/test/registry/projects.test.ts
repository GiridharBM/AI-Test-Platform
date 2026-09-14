import { beforeEach, describe, expect, it } from 'vitest'

import {
  clearLocalProjects,
  getLocalProjects,
  registerLocalProject,
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
})