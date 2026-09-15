import { AUTO_PIPELINE_STAGES, STAGE_LABELS, overallStatusLabel, stageKeyFromCurrentStage } from '../api/labels'
import type { PipelineOverallStatus } from '../api/types'

type StepState = 'done' | 'active' | 'pending'

const STEP_STATE_WORD: Record<StepState, string> = {
  done: 'done',
  active: 'in progress',
  pending: 'pending',
}

const STEP_STATE_CLASS: Record<StepState, string> = {
  done: 'border-emerald-600/40 bg-emerald-600/15 text-emerald-300',
  active: 'border-sky-500/60 bg-sky-600/15 text-sky-300',
  pending: 'border-slate-700/60 bg-slate-800/60 text-slate-400',
}

interface PipelineProgressProps {
  currentStage: string
  completedStages: string[]
  overallStatus?: PipelineOverallStatus
  userDecisionRequired?: boolean
}

export function PipelineProgress({
  currentStage,
  completedStages,
  overallStatus,
  userDecisionRequired,
}: PipelineProgressProps) {
  const activeKey = stageKeyFromCurrentStage(currentStage)
  const completed = new Set(completedStages)

  function stepState(stage: string): StepState {
    if (completed.has(stage)) {
      return 'done'
    }
    if (stage === activeKey) {
      return 'active'
    }
    return 'pending'
  }

  return (
    <div>
      {(overallStatus !== undefined || userDecisionRequired) && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {overallStatus !== undefined && (
            <span
              role="status"
              className="rounded-md border border-slate-600/50 bg-slate-700/60 px-2.5 py-1 text-sm"
              aria-label={`Pipeline outcome: ${overallStatusLabel(overallStatus)}`}
            >
              Outcome: {overallStatusLabel(overallStatus)}
            </span>
          )}
          {userDecisionRequired && (
            <span
              role="status"
              className="rounded-md border border-amber-600/40 bg-amber-950/20 px-2.5 py-1 text-sm text-amber-300"
              aria-label="Pipeline decision gate"
            >
              Waiting for a decision
            </span>
          )}
        </div>
      )}
      <ol className="flex flex-wrap items-center gap-2" aria-label="Pipeline stages">
        {AUTO_PIPELINE_STAGES.map((stage, index) => {
          const state = stepState(stage)
          const label = STAGE_LABELS[stage] ?? stage
          return (
            <li key={stage} className="flex items-center gap-2">
              <span
                className={`rounded-md border px-2.5 py-1 text-sm ${STEP_STATE_CLASS[state]}`}
                aria-label={`${label}: ${STEP_STATE_WORD[state]}`}
              >
                <span aria-hidden="true">{index + 1}.</span> {label}
                <span className="ml-1.5 text-xs uppercase tracking-wide text-slate-300/70">
                  · {STEP_STATE_WORD[state]}
                </span>
              </span>
              {index < AUTO_PIPELINE_STAGES.length - 1 && (
                <span aria-hidden="true" className="text-slate-600">
                  →
                </span>
              )}
            </li>
          )
        })}
      </ol>
      <p className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span className="rounded-md border border-dashed border-slate-600/60 bg-slate-900/40 px-2.5 py-1 text-slate-500">
          M10 · Evaluation
        </span>
        <span>Standalone — not part of the automatic pipeline chain.</span>
      </p>
    </div>
  )
}