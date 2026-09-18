export interface LocalProject {
  id: string
  name: string
  createdAt?: string
  origin?: 'upload' | 'path'
  fileCount?: number
  profiled?: boolean
}

export interface LocalProjectInput {
  id: string
  name: string
  createdAt?: string
  origin?: 'upload' | 'path'
  fileCount?: number
  profiled?: boolean
}

export interface RegistryRead {
  projects: LocalProject[]
  recovered: boolean
}

const STORAGE_KEY = 'auto-testing.projects'

function normalizeCreatedAt(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined
}

function normalizeOrigin(value: unknown): 'upload' | 'path' | undefined {
  return value === 'upload' || value === 'path' ? value : undefined
}

function normalizeFileCount(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return undefined
  }
  if (!Number.isInteger(value) || value < 0) {
    return undefined
  }
  return value
}

function normalizeProfiled(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined
}

function normalizeEntry(value: unknown): LocalProject | null {
  if (value === null || typeof value !== 'object') {
    return null
  }
  const v = value as Record<string, unknown>
  if (typeof v.id !== 'string' || v.id.length === 0) {
    return null
  }
  if (typeof v.name !== 'string') {
    return null
  }
  return {
    id: v.id,
    name: v.name,
    createdAt: normalizeCreatedAt(v.createdAt),
    origin: normalizeOrigin(v.origin),
    fileCount: normalizeFileCount(v.fileCount),
    profiled: normalizeProfiled(v.profiled),
  }
}

function removeStoredRegistry(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Storage unavailable: the in-memory result already returns the fallback.
  }
}

export function readLocalProjects(): RegistryRead {
  let raw: string | null = null
  try {
    raw = window.localStorage.getItem(STORAGE_KEY)
  } catch {
    return { projects: [], recovered: false }
  }
  if (raw === null) {
    return { projects: [], recovered: false }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(raw) as unknown
  } catch {
    removeStoredRegistry()
    return { projects: [], recovered: true }
  }
  if (!Array.isArray(parsed)) {
    removeStoredRegistry()
    return { projects: [], recovered: true }
  }
  const seen = new Set<string>()
  const projects: LocalProject[] = []
  for (const rawEntry of parsed) {
    const normalized = normalizeEntry(rawEntry)
    if (normalized === null) {
      continue
    }
    if (seen.has(normalized.id)) {
      continue
    }
    seen.add(normalized.id)
    projects.push(normalized)
  }
  return { projects, recovered: projects.length !== parsed.length }
}

export function getLocalProjects(): LocalProject[] {
  return readLocalProjects().projects
}

function writeRegistry(projects: LocalProject[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(projects))
  } catch {
    // Storage unavailable: the registry stays available for this session only.
  }
}

export function registerLocalProject(input: LocalProjectInput): LocalProject[] {
  const current = getLocalProjects().filter((p) => p.id !== input.id)
  const normalized = normalizeEntry(input)
  if (normalized === null) {
    return current
  }
  const updated = [normalized, ...current]
  writeRegistry(updated)
  return updated
}

export function removeLocalProject(id: string): LocalProject[] {
  const updated = getLocalProjects().filter((p) => p.id !== id)
  writeRegistry(updated)
  return updated
}

export function clearLocalProjects(): LocalProject[] {
  removeStoredRegistry()
  return []
}