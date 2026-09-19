import { useRef, useState } from 'react'

import type { ProjectDetails } from '../api/types'

import { ArtifactsOverview } from './ArtifactsOverview'

const TAB_PANEL_ID = 'artifact-tabpanel'

interface ArtifactTab {
  key: keyof ProjectDetails
  label: string
}

function tabId(key: string): string {
  return `artifact-tab-${key}`
}

const ARTIFACT_TABS: ArtifactTab[] = [
  { key: 'profile', label: 'Profile' },
  { key: 'codemap', label: 'Code map' },
  { key: 'test_plan', label: 'Test plan' },
  { key: 'test_generation', label: 'Generated tests' },
  { key: 'execution', label: 'Test execution' },
  { key: 'diagnosis', label: 'Diagnosis' },
  { key: 'improvement', label: 'Improvement' },
  { key: 'retest', label: 'Re-test' },
  { key: 'evaluation', label: 'Evaluation' },
  { key: 'repair', label: 'Source repair' },
]

function CodeBlock({ label, code }: { label: string; code: string }) {
  return (
    <div>
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <pre className="mt-1 max-w-full overflow-x-auto whitespace-pre rounded-md border border-slate-700 bg-slate-950 p-3 text-xs text-slate-300">
        {code}
      </pre>
    </div>
  )
}

interface ArtifactsTabsProps {
  project: ProjectDetails
}

function ProfileDetail({ project }: { project: ProjectDetails }) {
  const profile = project.profile
  if (!profile) return null
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-4">
        <div>
          <span className="text-slate-400">Languages:</span>{' '}
          {profile.languages.map((l) => l.name).join(', ') || '—'}
        </div>
        <div>
          <span className="text-slate-400">Complexity:</span>{' '}
          {profile.complexity.level}
        </div>
      </div>
      <div className="flex flex-wrap gap-4">
        <div>
          <span className="text-slate-400">Source files:</span>{' '}
          {profile.metrics.source_files}
        </div>
        <div>
          <span className="text-slate-400">Test files:</span>{' '}
          {profile.metrics.test_files}
        </div>
        <div>
          <span className="text-slate-400">Source lines:</span>{' '}
          {profile.metrics.source_lines}
        </div>
        <div>
          <span className="text-slate-400">Functions:</span>{' '}
          {profile.metrics.functions ?? '—'}
        </div>
      </div>
      <div>
        <span className="text-slate-400">Frameworks:</span>{' '}
        {profile.tests.frameworks.join(', ') || '—'}
      </div>
      {profile.warnings.length > 0 && (
        <ul className="list-inside list-disc text-amber-200/90">
          {profile.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
    </div>
  )
}

function CodemapDetail({ project }: { project: ProjectDetails }) {
  const codemap = project.codemap
  if (!codemap) return null
  const cs = codemap.coverage_summary
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-4">
        <div>
          <span className="text-slate-400">Source modules:</span>{' '}
          {codemap.source_modules.length}
        </div>
        <div>
          <span className="text-slate-400">Test functions:</span>{' '}
          {codemap.test_functions.length}
        </div>
        <div>
          <span className="text-slate-400">Test mappings:</span>{' '}
          {codemap.test_mappings.length}
        </div>
      </div>
      <div className="flex flex-wrap gap-4">
        <div>
          <span className="text-slate-400">Coverage:</span>{' '}
          {cs.coverage_percentage.toFixed(1)}%
        </div>
        <div>
          <span className="text-slate-400">Untested targets:</span>{' '}
          {cs.targets_without_tests}
        </div>
      </div>
      {codemap.warnings.length > 0 && (
        <ul className="list-inside list-disc text-amber-200/90">
          {codemap.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
    </div>
  )
}

function TestPlanDetail({ project }: { project: ProjectDetails }) {
  const plan = project.test_plan
  if (!plan) return null
  const s = plan.summary
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-4">
        <div>
          <span className="text-slate-400">Total specs:</span>{' '}
          {s.total_specs}
        </div>
        <div>
          <span className="text-slate-400">Critical:</span>{' '}
          {s.critical_count}
        </div>
        <div>
          <span className="text-slate-400">High:</span> {s.high_count}
        </div>
        <div>
          <span className="text-slate-400">Medium:</span>{' '}
          {s.medium_count}
        </div>
        <div>
          <span className="text-slate-400">Low:</span> {s.low_count}
        </div>
      </div>
      {plan.warnings.length > 0 && (
        <ul className="list-inside list-disc text-amber-200/90">
          {plan.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
    </div>
  )
}

function TestGenerationDetail({ project }: { project: ProjectDetails }) {
  const gen = project.test_generation
  if (!gen) return null
  const s = gen.summary
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-4">
        <div>
          <span className="text-slate-400">Files generated:</span>{' '}
          {s.total_files}
        </div>
        <div>
          <span className="text-slate-400">Test functions:</span>{' '}
          {s.total_test_functions}
        </div>
        <div>
          <span className="text-slate-400">Edge cases:</span>{' '}
          {s.total_edge_cases}
        </div>
        <div>
          <span className="text-slate-400">Framework:</span>{' '}
          {s.framework_used}
        </div>
      </div>
      {gen.files.length > 0 && (
        <div className="space-y-2">
          {gen.files.map((file) => (
            <details
              key={file.file_path}
              className="rounded-md border border-slate-700 bg-slate-900"
            >
              <summary className="cursor-pointer p-3 font-mono text-xs text-slate-200">
                {file.file_path} · {file.target_count} targets
              </summary>
              <div className="px-3 pb-3">
                <CodeBlock label="Content" code={file.content} />
              </div>
            </details>
          ))}
        </div>
      )}
      {gen.warnings.length > 0 && (
        <ul className="list-inside list-disc text-amber-200/90">
          {gen.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
    </div>
  )
}

function ExecutionDetail({ project }: { project: ProjectDetails }) {
  const exec = project.execution
  if (!exec) return null
  const s = exec.summary
  const filesWithTests = exec.file_results.some(
    (fr) => (fr.test_functions ?? []).length > 0,
  )
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-4">
        <div>
          <span className="text-slate-400">Overall:</span>{' '}
          {exec.overall_status}
        </div>
        <div>
          <span className="text-slate-400">Passed:</span> {s.passed}
        </div>
        <div>
          <span className="text-slate-400">Failed:</span> {s.failed}
        </div>
        <div>
          <span className="text-slate-400">Errors:</span> {s.errors}
        </div>
        <div>
          <span className="text-slate-400">Duration:</span>{' '}
          {exec.duration_seconds.toFixed(2)}s
        </div>
      </div>
      {exec.file_results.length > 0 && (
        <ul className="list-inside list-disc space-y-1">
          {exec.file_results.map((fr, i) => (
            <li key={i}>
              <details
                className="rounded-md border border-slate-700 bg-slate-900"
                open={filesWithTests && fr.status === 'failed'}
              >
                <summary className="cursor-pointer p-2">
                  <span className="font-mono text-xs text-slate-200">{fr.file_path}</span>{' '}
                  <span className="text-slate-500">({fr.status})</span>
                  {(fr.test_functions ?? []).length > 0 && (
                    <span className="ml-1 text-xs text-slate-500">
                      {fr.test_functions?.length} test{fr.test_functions?.length === 1 ? '' : 's'}
                    </span>
                  )}
                </summary>
                {(fr.test_functions ?? []).length > 0 ? (
                  <ul className="space-y-1 px-3 pb-3">
                    {fr.test_functions?.map((tf) => (
                      <li key={tf.test_function} className="flex items-center gap-2">
                        <span
                          className={
                            tf.status === 'passed'
                              ? 'text-emerald-400'
                              : tf.status === 'failed' || tf.status === 'error'
                                ? 'text-red-400'
                                : 'text-slate-500'
                          }
                        >
                          {tf.status}
                        </span>
                        <span className="font-mono text-xs text-slate-300">
                          {tf.test_function}
                        </span>
                        {tf.duration_seconds !== null &&
                          tf.duration_seconds !== undefined && (
                            <span className="text-xs text-slate-500">
                              {tf.duration_seconds.toFixed(3)}s
                            </span>
                          )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="px-3 pb-3 text-xs text-slate-500">
                    No per-test detail available for this file.
                  </p>
                )}
              </details>
            </li>
          ))}
        </ul>
      )}
      {exec.warnings.length > 0 && (
        <ul className="list-inside list-disc text-amber-200/90">
          {exec.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
    </div>
  )
}

function DiagnosisDetail({ project }: { project: ProjectDetails }) {
  const diag = project.diagnosis
  if (!diag) return null
  const s = diag.summary
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-4">
        <div>
          <span className="text-slate-400">Overall:</span>{' '}
          {diag.overall_status}
        </div>
        <div>
          <span className="text-slate-400">Findings:</span>{' '}
          {s.total_findings}
        </div>
        <div>
          <span className="text-slate-400">Potential bugs:</span>{' '}
          {s.potential_bugs}
        </div>
      </div>
      {diag.findings.length > 0 && (
        <ul className="space-y-2">
          {diag.findings.map((f) => (
            <li key={f.finding_id}>
              <details className="rounded-md border border-slate-700 bg-slate-900">
                <summary className="cursor-pointer p-3 text-sm">
                  <span className="text-slate-300">{f.test_function}</span>{' '}
                  <span className="text-slate-500">({f.category})</span>{' '}
                  <span className="text-slate-500">severity: {f.severity}</span>
                </summary>
                <div className="space-y-2 px-3 pb-3 text-sm">
                  {f.message !== '' && (
                    <p className="text-slate-300">{f.message}</p>
                  )}
                  {f.exception_type !== '' && (
                    <p className="text-slate-400">
                      Exception: {f.exception_type}
                    </p>
                  )}
                  {f.traceback !== '' && (
                    <CodeBlock label="Traceback" code={f.traceback} />
                  )}
                  {f.linked_locations.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-slate-500">
                        Linked locations
                      </p>
                      <ul className="mt-1 list-inside list-disc text-slate-300">
                        {f.linked_locations.map((loc, i) => (
                          <li key={i}>
                            {loc.source_file}:{loc.line_start}–{loc.line_end} (
                            {loc.qualified_name})
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </details>
            </li>
          ))}
        </ul>
      )}
      {diag.warnings.length > 0 && (
        <ul className="list-inside list-disc text-amber-200/90">
          {diag.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
    </div>
  )
}

function ImprovementDetail({ project }: { project: ProjectDetails }) {
  const imp = project.improvement
  if (!imp) return null
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-4">
        <div>
          <span className="text-slate-400">Status:</span> {imp.status}
        </div>
        <div>
          <span className="text-slate-400">Files modified:</span>{' '}
          {imp.files_modified}
        </div>
        <div>
          <span className="text-slate-400">Changes:</span>{' '}
          {imp.changes.length}
        </div>
      </div>
      {imp.changes.length > 0 && (
        <ul className="space-y-2">
          {imp.changes.map((c, i) => (
            <li key={i}>
              <details className="rounded-md border border-slate-700 bg-slate-900">
                <summary className="cursor-pointer p-3 text-sm">
                  <span className="text-slate-300">{c.test_function}</span>{' '}
                  <span className="text-slate-500">({c.status})</span>
                </summary>
                <div className="space-y-2 px-3 pb-3 text-sm">
                  {c.reason !== '' && (
                    <p className="text-slate-300">{c.reason}</p>
                  )}
                  <CodeBlock label="Before" code={c.before} />
                  <CodeBlock label="After" code={c.after} />
                </div>
              </details>
            </li>
          ))}
        </ul>
      )}
      {imp.warnings.length > 0 && (
        <ul className="list-inside list-disc text-amber-200/90">
          {imp.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
    </div>
  )
}

function RetestDetail({ project }: { project: ProjectDetails }) {
  const rt = project.retest
  if (!rt) return null
  const s = rt.summary
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-4">
        <div>
          <span className="text-slate-400">Status:</span> {rt.status}
        </div>
        <div>
          <span className="text-slate-400">Selected:</span> {s.selected}
        </div>
        <div>
          <span className="text-slate-400">Fixed:</span> {s.fixed}
        </div>
        <div>
          <span className="text-slate-400">Still failing:</span>{' '}
          {s.still_failing}
        </div>
        <div>
          <span className="text-slate-400">Regression:</span>{' '}
          {s.regression}
        </div>
      </div>
      {rt.comparisons.length > 0 && (
        <ul className="list-inside list-disc space-y-1">
          {rt.comparisons.map((c, i) => (
            <li key={i}>
              <span className="text-slate-300">{c.test_function}</span>{' '}
              <span className="text-slate-500">({c.verdict})</span>
            </li>
          ))}
        </ul>
      )}
      {rt.warnings.length > 0 && (
        <ul className="list-inside list-disc text-amber-200/90">
          {rt.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
    </div>
  )
}

function EvaluationDetail({ project }: { project: ProjectDetails }) {
  const ev = project.evaluation
  if (!ev) return null
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-4">
        <div>
          <span className="text-slate-400">Status:</span> {ev.status}
        </div>
        <div>
          <span className="text-slate-400">Line coverage:</span>{' '}
          {ev.coverage.status === 'completed'
            ? `${ev.coverage.line_percentage.toFixed(1)}%`
            : '—'}
        </div>
        <div>
          <span className="text-slate-400">Mutation score:</span>{' '}
          {ev.mutation.mutation_score !== null
            ? (ev.mutation.mutation_score * 100).toFixed(0)
            : '—'}
          %
        </div>
        {ev.benchmark.median_seconds !== null && (
          <div>
            <span className="text-slate-400">Median duration:</span>{' '}
            {ev.benchmark.median_seconds.toFixed(3)}s
          </div>
        )}
      </div>
      {ev.summary !== '' && (
        <p className="text-slate-300">{ev.summary}</p>
      )}
      {ev.warnings.length > 0 && (
        <ul className="list-inside list-disc text-amber-200/90">
          {ev.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
    </div>
  )
}

function RepairDetail({ project }: { project: ProjectDetails }) {
  const repair = project.repair
  if (!repair) return null

  const statusLine = (() => {
    if (repair.application_state === 'applied') {
      return project.origin === 'upload'
        ? 'Repair applied to the platform workspace copy.'
        : 'Repair applied to the project source.'
    }
    if (repair.approval_state === 'rejected') {
      return 'Repair was rejected and not applied.'
    }
    if (repair.approval_state === 'approved') {
      return 'Repair candidate approved. Awaiting application.'
    }
    if (
      repair.status === 'validated_pending_approval' ||
      (repair.selected_candidate !== null && repair.approval_state === 'pending')
    ) {
      return 'Repair candidate validated and awaiting approval.'
    }
    if (repair.attempts.length > 0) {
      return 'Repair candidate generated and being validated.'
    }
    return null
  })()

  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap gap-4">
        <div>
          <span className="text-slate-400">Status:</span> {repair.status}
        </div>
        <div>
          <span className="text-slate-400">Approval:</span>{' '}
          {repair.approval_state}
        </div>
        <div>
          <span className="text-slate-400">Application:</span>{' '}
          {repair.application_state}
        </div>
        <div>
          <span className="text-slate-400">Attempts:</span>{' '}
          {repair.attempts.length}
        </div>
      </div>
      {statusLine !== null && (
        <p
          className={
            repair.application_state === 'applied'
              ? 'text-emerald-300'
              : repair.approval_state === 'rejected'
                ? 'text-red-300'
                : 'text-amber-300'
          }
        >
          {statusLine}
        </p>
      )}
      {repair.final_validation.status !== 'not_run' && (
        <div>
          <span className="text-slate-400">Final validation:</span>{' '}
          {repair.final_validation.status}
          {repair.final_validation.reason !== '' && (
            <p className="mt-0.5 text-slate-300">
              {repair.final_validation.reason}
            </p>
          )}
        </div>
      )}
      {repair.selected_candidate !== null && (
        <details className="rounded-md border border-slate-700 bg-slate-900">
          <summary className="cursor-pointer p-3 text-sm font-medium text-slate-200">
            Candidate: {repair.selected_candidate.operation}
          </summary>
          <div className="space-y-2 px-3 pb-3 text-sm">
            <p className="text-slate-300">
              {repair.selected_candidate.file_path}:{' '}
              {repair.selected_candidate.source_location}
            </p>
            {repair.selected_candidate.rationale !== '' && (
              <p className="text-slate-300">
                {repair.selected_candidate.rationale}
              </p>
            )}
            <CodeBlock label="Before" code={repair.selected_candidate.before} />
            <CodeBlock label="After" code={repair.selected_candidate.after} />
          </div>
        </details>
      )}
      {repair.attempts.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-slate-500">Attempts</p>
          {repair.attempts.map((attempt) => (
            <details
              key={attempt.attempt_number}
              className="rounded-md border border-slate-700 bg-slate-900"
            >
              <summary className="cursor-pointer p-3 text-sm">
                <span className="text-slate-300">
                  Attempt {attempt.attempt_number}
                </span>{' '}
                <span className="text-slate-500">
                  validation: {attempt.validation_status}
                </span>
              </summary>
              <div className="space-y-2 px-3 pb-3 text-sm">
                {attempt.rationale !== '' && (
                  <p className="text-slate-300">{attempt.rationale}</p>
                )}
                {attempt.failure_reason !== '' && (
                  <p className="text-red-300">{attempt.failure_reason}</p>
                )}
                <CodeBlock label="Before" code={attempt.before} />
                <CodeBlock label="After" code={attempt.after} />
              </div>
            </details>
          ))}
        </div>
      )}
      {repair.warnings.length > 0 && (
        <ul className="list-inside list-disc text-amber-200/90">
          {repair.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
    </div>
  )
}

const DETAIL_RENDERERS: Partial<Record<string, React.ComponentType<{ project: ProjectDetails }>>> = {
  profile: ProfileDetail,
  codemap: CodemapDetail,
  test_plan: TestPlanDetail,
  test_generation: TestGenerationDetail,
  execution: ExecutionDetail,
  diagnosis: DiagnosisDetail,
  improvement: ImprovementDetail,
  retest: RetestDetail,
  evaluation: EvaluationDetail,
  repair: RepairDetail,
}

export function ArtifactsTabs({ project }: ArtifactsTabsProps) {
  const availableTabs = ARTIFACT_TABS.filter(
    ({ key }) => project[key] !== null && project[key] !== undefined,
  )
  const [activeTab, setActiveTab] = useState<string>(
    () => availableTabs[0]?.key ?? '',
  )
  const tabRefs = useRef(new Map<string, HTMLButtonElement>())

  function focusTab(key: string) {
    tabRefs.current.get(key)?.focus()
  }

  function onTablistKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const currentIndex = availableTabs.findIndex((t) => t.key === activeTab)
    if (currentIndex === -1) return
    let nextIndex = currentIndex
    switch (event.key) {
      case 'ArrowRight':
        nextIndex = (currentIndex + 1) % availableTabs.length
        break
      case 'ArrowLeft':
        nextIndex = (currentIndex - 1 + availableTabs.length) % availableTabs.length
        break
      case 'Home':
        nextIndex = 0
        break
      case 'End':
        nextIndex = availableTabs.length - 1
        break
      default:
        return
    }
    event.preventDefault()
    const nextKey = availableTabs[nextIndex].key
    setActiveTab(nextKey)
    focusTab(nextKey)
  }

  return (
    <div className="space-y-4">
      <ArtifactsOverview project={project} />

      {availableTabs.length === 0 ? (
        <p className="text-sm text-slate-400">
          No artifacts available yet.
        </p>
      ) : (
        <div>
          <div
            role="tablist"
            onKeyDown={onTablistKeyDown}
            className="flex gap-1 overflow-x-auto border-b border-slate-800"
          >
            {availableTabs.map(({ key, label }) => (
              <button
                key={key}
                ref={(node) => {
                  if (node) {
                    tabRefs.current.set(key, node)
                  } else {
                    tabRefs.current.delete(key)
                  }
                }}
                role="tab"
                type="button"
                id={tabId(key)}
                aria-selected={activeTab === key}
                aria-controls={TAB_PANEL_ID}
                tabIndex={activeTab === key ? 0 : -1}
                onClick={() => setActiveTab(key)}
                className={
                  activeTab === key
                    ? 'shrink-0 border-b-2 border-amber-500 px-3 py-2 text-sm font-medium text-white'
                    : 'shrink-0 px-3 py-2 text-sm text-slate-400 hover:text-white'
                }
              >
                {label}
              </button>
            ))}
          </div>
          <div
            id={TAB_PANEL_ID}
            role="tabpanel"
            aria-labelledby={tabId(activeTab)}
            className="mt-3 rounded-lg border border-slate-800 bg-slate-900 p-4"
          >
            {activeTab !== '' && (() => {
              const Renderer = DETAIL_RENDERERS[activeTab]
              return Renderer ? <Renderer project={project} /> : null
            })()}
          </div>
        </div>
      )}
    </div>
  )
}
