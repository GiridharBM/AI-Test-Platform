import { isTerminalErrorStatus, overallStatusLabel } from '../api/labels'
import type { PipelineState } from '../api/types'

interface ErrorPanelProps {
  state: PipelineState
}

export function ErrorPanel({ state }: ErrorPanelProps) {
  if (!isTerminalErrorStatus(state.overall_status)) {
    return null
  }

  const heading = overallStatusLabel(state.overall_status)

  return (
    <div className="rounded-lg border border-red-800/60 bg-red-950/30 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-red-300">{heading}</h3>
        <span
          role="status"
          className="rounded border border-red-600/40 bg-red-900/30 px-2 py-0.5 font-mono text-xs text-red-400"
        >
          ({state.overall_status})
        </span>
      </div>

      {state.reason !== '' && (
        <p className="mt-2 text-sm text-red-200/90">{state.reason}</p>
      )}

      {state.error !== '' && (
        <div className="mt-3 rounded-md border border-red-600/40 bg-red-900/30 p-3">
          <p className="text-sm font-medium text-red-300">Fatal error</p>
          <p className="mt-0.5 text-sm text-red-200/90">{state.error}</p>
        </div>
      )}

      {state.warnings.length > 0 && (
        <ul className="mt-3 list-inside list-disc space-y-0.5 text-sm text-amber-200/90">
          {state.warnings.map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
