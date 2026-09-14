import { Link } from 'react-router-dom'

interface ProjectHeaderProps {
  projectId: string
  name?: string
  fallbackName?: string
  loading?: boolean
}

export function ProjectHeader({
  projectId,
  name,
  fallbackName,
  loading = false,
}: ProjectHeaderProps) {
  const displayName = name || fallbackName
  const showingRegistryHint = displayName === fallbackName && fallbackName !== undefined && name === undefined

  return (
    <header
      aria-busy={loading}
      className="flex flex-wrap items-start justify-between gap-4"
    >
      <div>
        <h1 className="text-2xl font-semibold">Project Workspace</h1>
        {displayName !== undefined ? (
          <p className="mt-1 text-lg">
            <span>{displayName}</span>
            {showingRegistryHint && (
              <span className="text-sm text-slate-500">
                {' '}
                (from local registry — loading authoritative details…)
              </span>
            )}
          </p>
        ) : loading ? (
          <p className="mt-1 text-sm text-slate-400">Loading project details…</p>
        ) : null}
        <p className="mt-1 font-mono text-sm text-slate-400">
          Project ID: {projectId}
        </p>
      </div>
      <Link
        to="/"
        className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
      >
        ← Back to dashboard
      </Link>
    </header>
  )
}