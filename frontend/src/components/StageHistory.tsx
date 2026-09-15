import { STAGE_LABELS, formatTimestamp, stageStatusLabel } from '../api/labels'
import type { StageRecord } from '../api/types'

const STATUS_CLASS: Record<string, string> = {
  success: 'bg-emerald-600/15 text-emerald-300',
  approved: 'bg-emerald-600/15 text-emerald-300',
  failed: 'bg-red-600/15 text-red-300',
  blocked: 'bg-amber-600/15 text-amber-300',
  rejected: 'bg-red-600/15 text-red-300',
  unavailable: 'bg-slate-700/60 text-slate-300',
  skipped: 'bg-slate-700/60 text-slate-300',
  exhausted: 'bg-amber-600/15 text-amber-300',
  in_progress: 'bg-sky-600/15 text-sky-300',
}

interface StageHistoryProps {
  records: StageRecord[]
}

export function StageHistory({ records }: StageHistoryProps) {
  if (records.length === 0) {
    return <p className="text-sm text-slate-400">No stage history recorded yet.</p>
  }

  return (
    <ol className="space-y-2">
      {records.map((record, index) => {
        const stageLabel = STAGE_LABELS[record.stage] ?? record.stage
        const statusLabel = stageStatusLabel(record.status)
        const statusClass = STATUS_CLASS[record.status] ?? 'bg-slate-700/60 text-slate-300'
        return (
          <li
            key={`${record.stage}-${index}`}
            className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">
                {stageLabel}{' '}
                <span className="font-mono text-xs text-slate-500">
                  ({record.stage})
                </span>
              </span>
              <span
                className={`rounded px-2 py-0.5 text-xs ${statusClass}`}
                role="status"
              >
                {statusLabel}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Started {formatTimestamp(record.start_time)} · Ended{' '}
              {formatTimestamp(record.end_time)}
            </p>
            {record.result_id !== '' && (
              <p className="mt-1 text-sm text-slate-300">
                Result: {record.result_id}
              </p>
            )}
            {record.reason !== '' && (
              <p className="mt-1 text-sm text-slate-300">
                Reason: {record.reason}
              </p>
            )}
            {record.warnings.length > 0 && (
              <ul className="mt-1 list-inside list-disc space-y-0.5 text-sm text-amber-200/90">
                {record.warnings.map((warning, warningIndex) => (
                  <li key={warningIndex}>{warning}</li>
                ))}
              </ul>
            )}
          </li>
        )
      })}
    </ol>
  )
}