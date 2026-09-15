import { Link, useParams } from 'react-router-dom'

import { apiErrorMessage, ApiError } from '../api/client'
import { isTerminalErrorStatus } from '../api/labels'
import { ArtifactsTabs } from '../components/ArtifactsTabs'
import { CompletionPanel } from '../components/CompletionPanel'
import { DecisionCard } from '../components/DecisionCard'
import { ErrorPanel } from '../components/ErrorPanel'
import { PipelineProgress } from '../components/PipelineProgress'
import { PipelineStatus } from '../components/PipelineStatus'
import { ProjectHeader } from '../components/ProjectHeader'
import { StageHistory } from '../components/StageHistory'
import { usePipeline } from '../hooks/usePipeline'
import { useProject } from '../hooks/useProject'
import { useProjectRegistry } from '../hooks/useProjectRegistry'

function apiStatus(error: unknown): number | null {
  return error instanceof ApiError ? error.status : null
}

export function ProjectWorkspacePage() {
  const { id = '' } = useParams<{ id: string }>()
  const { projects } = useProjectRegistry()
  const localProject = projects.find((p) => p.id === id)

  const projectQuery = useProject(id)
  const pipelineQuery = usePipeline(id)

  const projectFailed =
    projectQuery.isError && projectQuery.data === undefined
  const projectNotFound =
    projectFailed && apiStatus(projectQuery.error) === 404

  const pipelineFailed =
    pipelineQuery.isError && pipelineQuery.data === undefined
  const pipelineNotFound =
    pipelineFailed && apiStatus(pipelineQuery.error) === 404

  const pipelineUpdating =
    pipelineQuery.isFetching && pipelineQuery.data !== undefined

  const p = pipelineQuery.data
  const isTerminalError = p !== undefined && isTerminalErrorStatus(p.overall_status)

  return (
    <div className="space-y-8">
      <ProjectHeader
        projectId={id}
        name={projectQuery.data?.name}
        fallbackName={localProject?.name}
        loading={projectQuery.isPending}
        pipeline={p !== undefined ? { current_stage: p.current_stage, overall_status: p.overall_status, user_decision_required: p.user_decision_required } : undefined}
      />

      <section aria-label="Pipeline status" className="space-y-4">
        <h2 className="text-lg font-semibold">Pipeline</h2>

        {pipelineQuery.isPending && pipelineQuery.data === undefined && (
          <p aria-busy="true" className="text-sm text-slate-400">
            Loading pipeline state…
          </p>
        )}

        {pipelineNotFound && (
          <p className="text-sm text-slate-400">
            Pipeline state is not available yet. The pipeline starts
            automatically after upload.
          </p>
        )}

        {pipelineFailed && !pipelineNotFound && (
          <div className="rounded-lg border border-red-800/60 bg-red-950/30 p-4">
            <p className="text-sm font-medium text-red-300">
              Could not load pipeline state.
            </p>
            <p className="mt-1 text-xs text-red-200/70">
              Error: {apiErrorMessage(pipelineQuery.error)}
            </p>
            <button
              type="button"
              onClick={() => void pipelineQuery.refetch()}
              disabled={pipelineQuery.isFetching}
              className="mt-3 rounded-md bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-600 disabled:opacity-50"
            >
              Retry
            </button>
          </div>
        )}

        {p !== undefined && (
          <>
            {isTerminalError ? (
              <ErrorPanel state={p} />
            ) : (
              <PipelineStatus state={p} />
            )}
            {p.overall_status === 'completed' && projectQuery.data !== undefined && (
              <CompletionPanel project={projectQuery.data} />
            )}
            <DecisionCard projectId={id} state={p} />
            <PipelineProgress
              currentStage={p.current_stage}
              completedStages={p.completed_stages}
              overallStatus={p.overall_status}
              userDecisionRequired={p.user_decision_required}
            />
            {pipelineUpdating && (
              <p role="status" className="text-xs text-slate-500">
                Updating…
              </p>
            )}
          </>
        )}
      </section>

      <section aria-label="Stage history" className="space-y-3">
        <h2 className="text-lg font-semibold">Stage History</h2>
        <StageHistory records={pipelineQuery.data?.stage_history ?? []} />
      </section>

      <section aria-label="Artifacts" className="space-y-3">
        <h2 className="text-lg font-semibold">Artifacts</h2>

        {projectQuery.isPending && projectQuery.data === undefined && (
          <p aria-busy="true" className="text-sm text-slate-400">
            Loading project details…
          </p>
        )}

        {projectFailed && projectNotFound && (
          <div className="rounded-lg border border-red-800/60 bg-red-950/30 p-4">
            <p className="text-sm font-medium text-red-300">
              Project not found.
            </p>
            <p className="mt-1 text-xs text-red-200/70">
              This project may have been removed.
            </p>
            <Link
              to="/"
              className="mt-3 inline-block rounded-md bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-600"
            >
              Back to dashboard
            </Link>
          </div>
        )}

        {projectFailed && !projectNotFound && (
          <div className="rounded-lg border border-red-800/60 bg-red-950/30 p-4">
            <p className="text-sm font-medium text-red-300">
              Could not load project details.
            </p>
            <p className="mt-1 text-xs text-red-200/70">
              Error: {apiErrorMessage(projectQuery.error)}
            </p>
            <button
              type="button"
              onClick={() => void projectQuery.refetch()}
              disabled={projectQuery.isFetching}
              className="mt-3 rounded-md bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-600 disabled:opacity-50"
            >
              Retry
            </button>
          </div>
        )}

        {projectQuery.data !== undefined && (
          <ArtifactsTabs project={projectQuery.data} />
        )}
      </section>
    </div>
  )
}