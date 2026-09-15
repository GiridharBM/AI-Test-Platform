import type { ProjectDetails } from '../api/types'

interface CompletionPanelProps {
  project: ProjectDetails
}

export function CompletionPanel({ project }: CompletionPanelProps) {
  const repair = project.repair

  return (
    <div className="rounded-lg border border-emerald-800/40 bg-emerald-950/20 p-4">
      <h3 className="text-sm font-semibold text-emerald-300">
        Pipeline completed
      </h3>

      {repair !== null && (
        <ul className="mt-2 space-y-1 text-sm text-slate-200">
          {repair.final_validation.status === 'passed' && (
            <li className="text-emerald-300">Repair validated</li>
          )}
          {repair.approval_state === 'approved' && (
            <li className="text-emerald-300">Repair approved</li>
          )}
          {repair.application_state === 'applied' && (
            <li className="text-emerald-300">
              {project.origin === 'upload'
                ? 'Repair applied to the platform workspace copy.'
                : 'Repair applied to the project source.'}
            </li>
          )}
          {repair.application_state === 'not_applied' && repair.approval_state === 'pending' && (
            <li className="text-amber-300">
              Repair candidate is validated and awaiting approval.
            </li>
          )}
          {repair.approval_state === 'rejected' && (
            <li className="text-red-300">
              Repair was rejected and not applied.
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
