import { Link } from 'react-router-dom'

import { currentStageLabel, overallStatusLabel } from '../api/labels'
import type { PipelineOverallStatus } from '../api/types'

interface ProjectHeaderProps {
  projectId: string
  name?: string
  fallbackName?: string
  loading?: boolean
  pipeline?: {
    current_stage: string
    overall_status: PipelineOverallStatus
    user_decision_required: boolean
  }
}

export function ProjectHeader({
  projectId,
  name,
  fallbackName,
  loading = false,
  pipeline,
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
      {pipeline !== undefined && (
        <div className="flex flex-wrap gap-2" aria-label="Pipeline summary">
          <span className="rounded-md border border-slate-600/50 bg-slate-700/60 px-2.5 py-1 text-sm">
            Stage: {currentStageLabel(pipeline.current_stage)}
          </span>
          <span className="rounded-md border border-slate-600/50 bg-slate-700/60 px-2.5 py-1 text-sm">
            Status: {overallStatusLabel(pipeline.overall_status)}
          </span>
          {pipeline.user_decision_required && (
            <span className="rounded-md border border-amber-600/40 bg-amber-950/20 px-2.5 py-1 text-sm text-amber-300">
              Action required
            </span>
          )}
        </div>
      )}
      <Link
        to="/"
        className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
      >
        ← Back to dashboard
      </Link>
    </header>
  )
}