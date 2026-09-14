import { AUTO_PIPELINE_STAGES, STAGE_LABELS, stageKeyFromCurrentStage } from '../api/labels'

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
}

export function PipelineProgress({
  currentStage,
  completedStages,
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