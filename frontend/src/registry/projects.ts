export interface LocalProject {
  id: string
  name: string
  createdAt?: string
}

const STORAGE_KEY = 'auto-testing.projects'

function isLocalProject(value: unknown): value is LocalProject {
  if (value === null || typeof value !== 'object') {
    return false
  }
  const v = value as { id?: unknown; name?: unknown }
  return typeof v.id === 'string' && v.id.length > 0 && typeof v.name === 'string'
}

function removeStoredRegistry(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Storage unavailable: the in-memory result already returns the fallback.
  }
}

export function getLocalProjects(): LocalProject[] {
  let raw: string | null = null
  try {
    raw = window.localStorage.getItem(STORAGE_KEY)
  } catch {
    return []
  }
  if (raw === null) {
    return []
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(raw) as unknown
  } catch {
    removeStoredRegistry()
    return []
  }
  if (!Array.isArray(parsed)) {
    removeStoredRegistry()
    return []
  }
  const valid = parsed.filter(isLocalProject)
  const seen = new Set<string>()
  return valid.filter((p) => {
    if (seen.has(p.id)) {
      return false
    }
    seen.add(p.id)
    return true
  })
}

function writeRegistry(projects: LocalProject[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(projects))
  } catch {
    // Storage unavailable: the registry stays available for this session only.
  }
}

export function registerLocalProject(
  project: { id: string; name: string; createdAt?: string },
): LocalProject[] {
  const current = getLocalProjects().filter((p) => p.id !== project.id)
  const updated = [
    { id: project.id, name: project.name, createdAt: project.createdAt },
    ...current,
  ]
  writeRegistry(updated)
  return updated
}

export function clearLocalProjects(): LocalProject[] {
  removeStoredRegistry()
  return []
}