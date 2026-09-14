import { apiErrorMessage } from '../api/client'
import { actionLabel } from '../api/labels'
import type { PipelineState } from '../api/types'
import { usePipelineAction } from '../hooks/usePipeline'

interface PipelineActionsProps {
  projectId: string
  state: PipelineState
}

const PRIMARY_ACTIONS = new Set(['retest', 'repair', 'approve'])

export function PipelineActions({ projectId, state }: PipelineActionsProps) {
  const mutation = usePipelineAction(projectId)
  const actions = state.user_decision_required
    ? state.available_actions
    : []

  if (actions.length === 0) {
    return null
  }

  return (
    <div className="rounded-lg border border-amber-600/40 bg-amber-950/20 p-4">
      <h3 className="text-sm font-semibold text-amber-300">
        Decision required
      </h3>
      {state.reason !== '' && (
        <p className="mt-1 text-sm text-amber-100/80">{state.reason}</p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {actions.map((action) => (
          <button
            key={action}
            type="button"
            onClick={() => mutation.mutate(action)}
            disabled={mutation.isPending}
            aria-label={actionLabel(action)}
            className={
              PRIMARY_ACTIONS.has(action)
                ? 'rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-slate-950 hover:bg-amber-500 disabled:opacity-50'
                : 'rounded-md border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50'
            }
          >
            {actionLabel(action)}
          </button>
        ))}
        {mutation.isPending && (
          <span role="status" className="self-center text-xs text-slate-300">
            Working…
          </span>
        )}
      </div>

      {mutation.isError && mutation.error !== null && (
        <p role="alert" className="mt-3 text-sm text-red-300">
          Action failed: {apiErrorMessage(mutation.error)}
        </p>
      )}
    </div>
  )
}