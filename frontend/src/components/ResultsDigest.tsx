import { apiErrorMessage, ApiError } from '../api/client'
import type { DigestVerdict } from '../api/types'
import { useResultsDigest } from '../hooks/useResultsDigest'

interface ResultsDigestProps {
  projectId: string
}

const VERDICT_LABEL: Record<DigestVerdict, string> = {
  passed: 'Passed',
  failed: 'Failed',
  no_execution: 'No execution yet',
  blocked: 'Blocked',
  unavailable: 'Unavailable',
  repair_pending: 'Repair awaiting approval',
  rejected: 'Repair rejected',
}

const VERDICT_STYLE: Record<DigestVerdict, string> = {
  passed: 'border-emerald-800/40 bg-emerald-950/20 text-emerald-300',
  failed: 'border-red-800/60 bg-red-950/30 text-red-300',
  no_execution: 'border-slate-700 bg-slate-900 text-slate-300',
  blocked: 'border-amber-800/60 bg-amber-950/30 text-amber-300',
  unavailable: 'border-amber-800/60 bg-amber-950/30 text-amber-300',
  repair_pending: 'border-amber-800/60 bg-amber-950/30 text-amber-300',
  rejected: 'border-red-800/60 bg-red-950/30 text-red-300',
}

function Section({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div
      role="region"
      aria-label={label}
      className="rounded-lg border border-slate-800 bg-slate-900 p-4"
    >
      <h3 className="text-sm font-semibold text-slate-200">{label}</h3>
      <div className="mt-2 space-y-1 text-sm text-slate-300">{children}</div>
    </div>
  )
}

function Kvp({
  label,
  value,
}: {
  label: string
  value: string | number
}) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-slate-400">{label}:</span>{' '}
      <span className="text-slate-200">{value}</span>
    </div>
  )
}

function VerdictBadge({ verdict, reason }: { verdict: DigestVerdict; reason: string }) {
  return (
    <div className={`rounded-lg border p-4 ${VERDICT_STYLE[verdict]}`}>
      <p className="text-lg font-semibold">
        <span role="img" aria-label={`${VERDICT_LABEL[verdict]} result`}>
          {verdict === 'passed' ? '✓' : verdict === 'failed' || verdict === 'rejected' ? '✕' : '•'}
        </span>{' '}
        {VERDICT_LABEL[verdict]}
      </p>
      {reason !== '' && <p className="mt-1 text-sm text-slate-300">{reason}</p>}
    </div>
  )
}

export function ResultsDigest({ projectId }: ResultsDigestProps) {
  const query = useResultsDigest(projectId)

  if (query.isPending && query.data === undefined) {
    return (
      <div aria-busy="true" className="text-sm text-slate-400">
        Loading results summary…
      </div>
    )
  }

  if (query.isError && query.data === undefined) {
    const notFound =
      query.error instanceof ApiError && query.error.status === 404
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <p className="text-sm font-medium text-slate-300">
          {notFound ? 'Results are not available for this project.' : 'Could not load results.'}
        </p>
        {!notFound && (
          <>
            <p className="mt-1 text-xs text-red-200/70">
              Error: {apiErrorMessage(query.error)}
            </p>
            <button
              type="button"
              onClick={() => void query.refetch()}
              disabled={query.isFetching}
              className="mt-3 rounded-md bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-600 disabled:opacity-50"
            >
              Retry
            </button>
          </>
        )}
      </div>
    )
  }

  const d = query.data
  if (d === undefined) return null
  const counts = d.test_counts
  const repair = d.repair

  return (
    <div className="space-y-3">
      <VerdictBadge verdict={d.overall_verdict} reason={d.reason} />

      {d.warnings.length > 0 && (
        <ul className="list-inside list-disc text-amber-200/90">
          {d.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}

      {d.execution_status !== null && (
        <Section label="Execution">
          <Kvp label="Status" value={d.execution_status} />
          {d.execution_duration_seconds !== null && (
            <Kvp label="Duration" value={`${d.execution_duration_seconds.toFixed(2)}s`} />
          )}
          {counts !== null && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1">
              <Kvp label="Files" value={counts.total_files} />
              <Kvp label="Tests" value={counts.total_test_functions} />
              <Kvp label="Passed" value={counts.passed} />
              <Kvp label="Failed" value={counts.failed} />
              <Kvp label="Errors" value={counts.errors} />
              <Kvp label="Skipped" value={counts.skipped} />
            </div>
          )}
        </Section>
      )}

      {d.pipeline_status !== null && (
        <Section label="Pipeline">
          <Kvp label="Status" value={d.pipeline_status} />
          {d.pipeline_current_stage !== null && (
            <Kvp label="Current stage" value={d.pipeline_current_stage} />
          )}
        </Section>
      )}

      {(d.diagnosis_status !== null || d.failing_tests.length > 0) && (
        <Section label="Diagnosis">
          {d.diagnosis_status !== null && <Kvp label="Status" value={d.diagnosis_status} />}
          {d.failing_tests.length === 0 ? (
            <p className="text-slate-400">No failing tests.</p>
          ) : (
            <ul className="space-y-2 pt-1">
              {d.failing_tests.map((ft) => (
                <li
                  key={`${ft.test_file}:${ft.test_function}`}
                  className="rounded-md border border-slate-800 bg-slate-950 p-2"
                >
                  <p className="font-mono text-xs text-slate-200">
                    {ft.test_function} <span className="text-slate-500">({ft.status})</span>
                  </p>
                  {ft.source_file !== '' && (
                    <p className="mt-0.5 text-xs text-slate-400">
                      {ft.source_file}
                      {ft.source_line_start !== null && `:${ft.source_line_start}`}
                      {ft.source_qualified_name !== '' && ` · ${ft.source_qualified_name}`}
                    </p>
                  )}
                  {ft.message !== '' && (
                    <p className="mt-0.5 text-xs text-slate-400">{ft.message}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}

      {(d.improvement_status !== null ||
        d.retest_status !== null ||
        d.repair !== null ||
        d.evaluation !== null) && (
        <Section label="Improvement, repair & evaluation">
          {d.improvement_status !== null && (
            <Kvp
              label="Improvement"
              value={`${d.improvement_status}${
                d.improvement_files_modified !== null
                  ? ` (${d.improvement_files_modified} file${
                      d.improvement_files_modified === 1 ? '' : 's'
                    } modified)`
                  : ''
              }`}
            />
          )}
          {d.retest_status !== null && (
            <Kvp label="Re-test" value={d.retest_status} />
          )}
          {repair !== null && (
            <div className="border-t border-slate-800 pt-2">
              <Kvp label="Repair" value={repair.approval_state} />
              {repair.selected_file_path !== '' && (
                <Kvp label="Repair target" value={repair.selected_file_path} />
              )}
              {repair.final_validation_status !== '' && (
                <Kvp label="Final validation" value={repair.final_validation_status} />
              )}
              {repair.final_validation_reason !== '' && (
                <p className="text-xs text-slate-400">{repair.final_validation_reason}</p>
              )}
              {repair.reasons.length > 0 && (
                <ul className="list-inside list-disc text-xs text-slate-400">
                  {repair.reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              )}
            </div>
          )}
          {d.evaluation !== null && (
            <div className="border-t border-slate-800 pt-2">
              <Kvp label="Evaluation" value={d.evaluation.status} />
              {d.evaluation.coverage_status === 'completed' &&
                d.evaluation.line_coverage_percentage !== null && (
                  <Kvp
                    label="Line coverage"
                    value={`${d.evaluation.line_coverage_percentage.toFixed(1)}%`}
                  />
                )}
              {d.evaluation.mutation_status === 'completed' &&
                d.evaluation.mutation_score !== null && (
                  <Kvp label="Mutation score" value={`${d.evaluation.mutation_score.toFixed(1)}%`} />
                )}
              {d.evaluation.benchmark_status === 'completed' &&
                d.evaluation.benchmark_median_seconds !== null && (
                  <Kvp
                    label="Median duration"
                    value={`${d.evaluation.benchmark_median_seconds.toFixed(3)}s`}
                  />
                )}
            </div>
          )}
        </Section>
      )}
    </div>
  )
}