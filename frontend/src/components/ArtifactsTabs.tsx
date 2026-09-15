import { useState } from 'react'

import type { ProjectDetails } from '../api/types'

import { ArtifactsOverview } from './ArtifactsOverview'

interface ArtifactTab {
  key: keyof ProjectDetails
  label: string
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
        <div className="overflow-x-auto">
          <pre className="rounded-md border border-slate-700 bg-slate-900 p-3 text-xs text-slate-300">
            {gen.files.map((f) => f.file_path).join('\n')}
          </pre>
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
              <span className="text-slate-300">{fr.file_path}</span>{' '}
              <span className="text-slate-500">({fr.status})</span>
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
        <ul className="list-inside list-disc space-y-1">
          {diag.findings.map((f) => (
            <li key={f.finding_id}>
              <span className="text-slate-300">{f.test_function}</span>{' '}
              <span className="text-slate-500">({f.category})</span>{' '}
              <span className="text-slate-500">severity: {f.severity}</span>
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
        <ul className="list-inside list-disc space-y-1">
          {imp.changes.map((c, i) => (
            <li key={i}>
              <span className="text-slate-300">{c.test_function}</span>{' '}
              <span className="text-slate-500">({c.status})</span>
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
      {repair.final_validation.status !== 'not_run' && (
        <div>
          <span className="text-slate-400">Final validation:</span>{' '}
          {repair.final_validation.status}
        </div>
      )}
      {repair.application_state === 'applied' && project.origin === 'upload' && (
        <p className="text-emerald-300">
          Repair applied to the platform workspace copy.
        </p>
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

  return (
    <div className="space-y-4">
      <ArtifactsOverview project={project} />

      {availableTabs.length === 0 ? (
        <p className="text-sm text-slate-400">
          No artifacts available yet.
        </p>
      ) : (
        <div>
          <div role="tablist" className="flex flex-wrap gap-1 border-b border-slate-800">
            {availableTabs.map(({ key, label }) => (
              <button
                key={key}
                role="tab"
                type="button"
                aria-selected={activeTab === key}
                onClick={() => setActiveTab(key)}
                className={
                  activeTab === key
                    ? 'border-b-2 border-amber-500 px-3 py-2 text-sm font-medium text-white'
                    : 'px-3 py-2 text-sm text-slate-400 hover:text-white'
                }
              >
                {label}
              </button>
            ))}
          </div>
          <div role="tabpanel" className="mt-3 rounded-lg border border-slate-800 bg-slate-900 p-4">
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
