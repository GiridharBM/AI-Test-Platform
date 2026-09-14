import { currentStageLabel, overallStatusLabel } from '../api/labels'
import type { PipelineState } from '../api/types'

interface PipelineStatusProps {
  state: PipelineState
}

export function PipelineStatus({ state }: PipelineStatusProps) {
  const {
    overall_status,
    current_stage,
    current_improvement_round,
    maximum_improvement_rounds,
    user_decision_required,
    reason,
    warnings,
    error,
  } = state

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          role="status"
          className="rounded-md border border-slate-600/50 bg-slate-700/60 px-2.5 py-1 text-sm font-medium"
        >
          {overallStatusLabel(overall_status)}{' '}
          <span className="font-mono text-xs text-slate-400">
            ({overall_status})
          </span>
        </span>
        <span
          role="status"
          className="rounded-md bg-slate-800 px-2.5 py-1 text-sm"
        >
          Stage: {currentStageLabel(current_stage)}
          <span className="font-mono text-xs text-slate-500">
            {' '}
            ({current_stage})
          </span>
        </span>
        {current_improvement_round > 0 && (
          <span
            role="status"
            className="rounded-md bg-slate-800 px-2.5 py-1 text-sm"
          >
            Improvement round {current_improvement_round} of{' '}
            {maximum_improvement_rounds}
          </span>
        )}
      </div>

      {user_decision_required && (
        <p role="status" className="mt-3 text-sm text-amber-300">
          A user decision is required before the pipeline can continue.
        </p>
      )}

      {reason !== '' && (
        <div role="status" className="mt-3">
          <p className="text-sm font-medium">Reason</p>
          <p className="mt-0.5 text-sm text-slate-300">{reason}</p>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="mt-3 rounded-md border border-amber-600/30 bg-amber-950/30 p-3">
          <p className="text-sm font-medium text-amber-300">Warnings</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5 text-sm text-amber-200/90">
            {warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {error !== '' && (
        <div className="mt-3 rounded-md border border-red-600/40 bg-red-950/30 p-3">
          <p className="text-sm font-medium text-red-300">Error</p>
          <p className="mt-0.5 text-sm text-red-200/90">{error}</p>
        </div>
      )}
    </div>
  )
}