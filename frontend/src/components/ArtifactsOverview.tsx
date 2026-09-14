import type { ProjectDetails } from '../api/types'

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
        return (
          <li
            key={key}
            className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3"
          >
            <span className="font-medium">{label}</span>
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