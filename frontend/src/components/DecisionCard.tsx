import { currentStageLabel } from '../api/labels'
import type { PipelineState } from '../api/types'

import { PipelineActions } from './PipelineActions'

interface DecisionCardProps {
  projectId: string
  state: PipelineState
}

export function DecisionCard({ projectId, state }: DecisionCardProps) {
  if (!state.user_decision_required) {
    return null
  }

  return (
    <div className="rounded-lg border border-amber-600/40 bg-amber-950/20 p-4">
      <h3 className="text-sm font-semibold text-amber-300">
        Decision required
      </h3>
      <p className="mt-1 text-sm text-amber-100/80">
        The pipeline is waiting for a decision before the{' '}
        {currentStageLabel(state.current_stage)} stage can proceed.
      </p>
      {state.reason !== '' && (
        <p className="mt-2 text-sm text-amber-100/80">
          Reason: {state.reason}
        </p>
      )}
      <div className="mt-3">
        <PipelineActions projectId={projectId} state={state} />
      </div>
    </div>
  )
}
