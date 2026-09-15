import type {
  CodeMap,
  DiagnosisResult,
  EvaluationResult,
  ExecutionStatus,
  ImprovementResult,
  ProjectDetails,
  ProjectProfile,
  RepairResult,
  ReTestResult,
  TestExecutionResult,
  TestGenerationResult,
  TestPlan,
} from '../api/types'

interface ArtifactDefinition {
  key: keyof ProjectDetails
  label: string
}

const ARTIFACTS: ArtifactDefinition[] = [
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

function artifactStatus(artifact: unknown): string | null {
  if (artifact === null || typeof artifact !== 'object') {
    return null
  }
  const record = artifact as Record<string, unknown>
  const status = record.overall_status ?? record.status
  return typeof status === 'string' && status !== '' ? status : null
}

type Tone = 'none' | 'warn' | 'error' | 'good'

const TONE_CLASS: Record<Tone, string> = {
  none: 'border-slate-800 bg-slate-900',
  warn: 'border-amber-700/50 bg-amber-950/20',
  error: 'border-red-800/50 bg-red-950/20',
  good: 'border-emerald-800/40 bg-emerald-950/10',
}

function executionTone(status: ExecutionStatus): Tone {
  if (status === 'failed' || status === 'error' || status === 'timeout') {
    return 'error'
  }
  if (status === 'passed') {
    return 'good'
  }
  return 'warn'
}

interface ArtifactSummary {
  summary: string | null
  tone: Tone
}

function summarizeArtifact(
  key: keyof ProjectDetails,
  artifact: unknown,
): ArtifactSummary {
  switch (key) {
    case 'profile': {
      const profile = artifact as ProjectProfile
      return {
        summary: `${profile.complexity.level} · ${profile.languages.map((l) => l.name).join(', ')}`,
        tone: 'none',
      }
    }
    case 'codemap': {
      const codemap = artifact as CodeMap
      return {
        summary: `${codemap.coverage_summary.coverage_percentage.toFixed(0)}% coverage`,
        tone: 'none',
      }
    }
    case 'test_plan': {
      const plan = artifact as TestPlan
      return {
        summary: `${plan.summary.total_specs} specs`,
        tone: 'none',
      }
    }
    case 'test_generation': {
      const gen = artifact as TestGenerationResult
      return {
        summary: `${gen.summary.total_files} files · ${gen.summary.total_test_functions} tests`,
        tone: 'none',
      }
    }
    case 'execution': {
      const execution = artifact as TestExecutionResult
      return {
        summary: `${execution.overall_status} · ${execution.summary.passed} passed · ${execution.summary.failed} failed`,
        tone: executionTone(execution.overall_status),
      }
    }
    case 'diagnosis': {
      const diagnosis = artifact as DiagnosisResult
      return {
        summary:
          diagnosis.summary.total_findings > 0
            ? `${diagnosis.summary.total_findings} failure${diagnosis.summary.total_findings === 1 ? '' : 's'} diagnosed`
            : 'no failures detected',
        tone: diagnosis.summary.total_findings > 0 ? 'warn' : 'good',
      }
    }
    case 'improvement': {
      const improvement = artifact as ImprovementResult
      return {
        summary: `${improvement.status} · ${improvement.files_modified} file${improvement.files_modified === 1 ? '' : 's'} modified`,
        tone: improvement.status === 'blocked' ? 'warn' : 'none',
      }
    }
    case 'retest': {
      const retest = artifact as ReTestResult
      const unresolved = retest.summary.still_failing + retest.summary.regression
      return {
        summary: unresolved > 0
          ? `${unresolved} still failing / regression`
          : retest.summary.fixed > 0
            ? `${retest.summary.fixed} fixed`
            : 'no failures',
        tone: unresolved > 0 ? 'error' : 'good',
      }
    }
    case 'evaluation': {
      const evaluation = artifact as EvaluationResult
      if (evaluation.coverage.status === 'completed') {
        return {
          summary: `${evaluation.coverage.line_percentage.toFixed(1)}% line coverage`,
          tone: 'good',
        }
      }
      return {
        summary: `coverage ${evaluation.coverage.status}`,
        tone: 'warn',
      }
    }
    case 'repair': {
      const repair = artifact as RepairResult
      if (repair.application_state === 'applied') {
        return { summary: 'applied', tone: 'good' }
      }
      if (repair.approval_state === 'rejected') {
        return { summary: 'rejected', tone: 'error' }
      }
      if (repair.approval_state === 'pending') {
        return { summary: 'awaiting approval', tone: 'warn' }
      }
      return { summary: repair.status, tone: 'none' }
    }
    default:
      return { summary: null, tone: 'none' }
  }
}

interface ArtifactsOverviewProps {
  project: ProjectDetails
}

export function ArtifactsOverview({ project }: ArtifactsOverviewProps) {
  return (
    <ul className="grid gap-2 sm:grid-cols-2">
      {ARTIFACTS.map(({ key, label }) => {
        const artifact = project[key]
        const available = artifact !== null && artifact !== undefined
        const status = artifactStatus(artifact)
        const { summary, tone } = available
          ? summarizeArtifact(key, artifact)
          : { summary: null, tone: 'none' as const }
        return (
          <li
            key={key}
            className={`flex items-center justify-between gap-3 rounded-lg border px-4 py-3 ${TONE_CLASS[tone]}`}
          >
            <div className="min-w-0">
              <span className="block font-medium">{label}</span>
              {available && summary !== null && (
                <span className="block truncate text-xs text-slate-400">
                  {summary}
                </span>
              )}
            </div>
            <span className="flex flex-wrap items-center justify-end gap-2">
              {status !== null && (
                <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-400">
                  {status}
                </span>
              )}
              <span
                className={`rounded px-2 py-0.5 text-xs ${
                  available
                    ? 'bg-emerald-600/10 text-emerald-400'
                    : 'bg-slate-800 text-slate-400'
                }`}
              >
                {available ? 'Available' : 'Not available'}
              </span>
            </span>
          </li>
        )
      })}
    </ul>
  )
}