import { apiErrorMessage } from '../api/client'
import type { ProjectDetails } from '../api/types'
import { useProjectExport } from '../hooks/useProjectExport'

interface CompletionPanelProps {
  project: ProjectDetails
}

export function CompletionPanel({ project }: CompletionPanelProps) {
  const repair = project.repair
  const exportMutation = useProjectExport(project.project_id)

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

      {project.origin === 'upload' && (
        <div className="mt-3 border-t border-emerald-800/40 pt-3">
          <p className="text-xs text-slate-300">
            Download the repaired project — a copy saved in the platform
            workspace. Your original upload is untouched.
          </p>
          <button
            type="button"
            onClick={() => exportMutation.mutate()}
            disabled={exportMutation.isPending}
            className="mt-2 rounded-md bg-emerald-700 px-3 py-1.5 text-sm text-white hover:bg-emerald-600 disabled:opacity-50"
          >
            {exportMutation.isPending ? 'Exporting…' : 'Download project export'}
          </button>
          {exportMutation.isError && (
            <p className="mt-2 text-xs text-red-300">
              Export failed: {apiErrorMessage(exportMutation.error)}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
