import { Link, useNavigate } from 'react-router-dom'

import type { ProjectMeta } from '../api/types'
import { UploadProject } from '../components/UploadProject'
import { useProjectRegistry } from '../hooks/useProjectRegistry'

export function DashboardPage() {
  const { projects, register, clear } = useProjectRegistry()
  const navigate = useNavigate()

  function handleUploaded(project: ProjectMeta): void {
    register({
      id: project.project_id,
      name: project.name,
      createdAt: project.created_at,
    })
    navigate(`/projects/${encodeURIComponent(project.project_id)}`)
  }

  return (
    <section className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-400">
          Upload a project to start the automated test pipeline.
        </p>
      </div>

      <UploadProject onUploaded={handleUploaded} />

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Registered Projects</h2>
          {projects.length > 0 && (
            <button
              type="button"
              onClick={clear}
              className="text-sm text-slate-400 underline-offset-2 hover:text-slate-200 hover:underline"
            >
              Clear list
            </button>
          )}
        </div>

        {projects.length === 0 ? (
          <p className="text-sm text-slate-400">
            No projects registered yet. Upload a project folder to begin.
          </p>
        ) : (
          <ul className="space-y-2">
            {projects.map((project) => (
              <li
                key={project.id}
                className="flex items-center justify-between gap-4 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium">{project.name}</p>
                  <p className="truncate font-mono text-xs text-slate-500">
                    {project.id}
                  </p>
                </div>
                <Link
                  to={`/projects/${encodeURIComponent(project.id)}`}
                  className="shrink-0 rounded-md bg-slate-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-600"
                >
                  Open Project
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}