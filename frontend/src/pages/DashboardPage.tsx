import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import type { ProjectMeta } from '../api/types'
import { UploadProject } from '../components/UploadProject'
import { useBackendProjects } from '../hooks/useBackendProjects'
import { useProjectRegistry } from '../hooks/useProjectRegistry'
import { mergeProjects, type LocalProject } from '../registry/projects'

function formatAddedDate(createdAt: string | undefined): string | null {
  if (createdAt === undefined) {
    return null
  }
  const date = new Date(createdAt)
  if (Number.isNaN(date.getTime())) {
    return null
  }
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function originLabel(origin: 'upload' | 'path'): string {
  return origin === 'upload' ? 'Upload' : 'Path'
}

interface MetaRow {
  label: string
  value: string
}

function projectMetaRows(project: LocalProject): MetaRow[] {
  const rows: MetaRow[] = []
  const added = formatAddedDate(project.createdAt)
  if (added !== null) {
    rows.push({ label: 'Added', value: added })
  }
  if (project.origin !== undefined) {
    rows.push({ label: 'Origin', value: originLabel(project.origin) })
  }
  if (project.fileCount !== undefined) {
    rows.push({ label: 'Files', value: String(project.fileCount) })
  }
  if (project.profiled !== undefined) {
    rows.push({
      label: 'Profile',
      value: project.profiled ? 'Profiled' : 'Not profiled',
    })
  }
  return rows
}

export function DashboardPage() {
  const { projects, register, remove, clear, recovered } = useProjectRegistry()
  const { data: backendProjects } = useBackendProjects()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [confirmingClear, setConfirmingClear] = useState(false)
  const cancelClearRef = useRef<HTMLButtonElement>(null)
  const confirmClearRef = useRef<HTMLButtonElement>(null)
  const clearTriggerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (confirmingClear) {
      clearTriggerRef.current = document.activeElement as HTMLElement | null
      cancelClearRef.current?.focus()
    }
  }, [confirmingClear])

  function closeClearDialog() {
    setConfirmingClear(false)
    requestAnimationFrame(() => clearTriggerRef.current?.focus())
  }

  function handleUploaded(project: ProjectMeta): void {
    register({
      id: project.project_id,
      name: project.name,
      createdAt: project.created_at,
      origin: project.origin,
      fileCount: project.file_count ?? undefined,
      profiled: project.profiled,
    })
    navigate(`/projects/${encodeURIComponent(project.project_id)}`)
  }

  const mergedProjects = useMemo(
    () => mergeProjects(projects, backendProjects ?? []),
    [projects, backendProjects],
  )
  const query = search.trim().toLowerCase()
  const visibleProjects = useMemo(
    () =>
      query === ''
        ? mergedProjects
        : mergedProjects.filter((project) =>
            project.name.toLowerCase().includes(query),
          ),
    [mergedProjects, query],
  )

  return (
    <div className="space-y-10">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="max-w-2xl text-sm text-slate-400">
          The AI Test Platform runs a privacy-preserving, automated testing
          pipeline for your software projects — profiling, test generation,
          execution, diagnosis, repair, and evaluation — without storing your
          code on the backend.
        </p>
      </header>

      <section aria-labelledby="upload-heading" className="space-y-3">
        <div>
          <h2 id="upload-heading" className="text-lg font-semibold">
            Upload a Project
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Start a new project. Choose a local project folder to begin the
            automated test pipeline.
          </p>
        </div>
        <UploadProject onUploaded={handleUploaded} />
      </section>

      <section aria-labelledby="projects-heading" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 id="projects-heading" className="text-lg font-semibold">
              Your Projects
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              Projects available on the backend appear here alongside saved
              references from this browser.
            </p>
          </div>
          {projects.length > 0 && (
            <button
              type="button"
              onClick={() => setConfirmingClear(true)}
              className="text-sm text-slate-400 underline-offset-2 hover:text-slate-200 hover:underline"
            >
              Clear saved list
            </button>
          )}
        </div>

        {recovered && (
          <p role="status" className="text-sm text-amber-200/90">
            Some saved project references could not be read and were skipped.
            The remaining saved projects are still listed below.
          </p>
        )}

        {mergedProjects.length > 0 && (
          <div className="space-y-2">
            <label htmlFor="project-search" className="block text-sm">
              Search projects
            </label>
            <input
              id="project-search"
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by project name"
              className="w-full max-w-md rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500"
            />
          </div>
        )}

        {mergedProjects.length === 0 ? (
          <div className="space-y-3 rounded-lg border border-dashed border-slate-700 bg-slate-900/50 p-6 text-center">
            <p className="text-sm text-slate-300">
              No projects registered yet. Projects added from this browser will
              appear here.
            </p>
            <p className="text-sm text-slate-500">
              Upload a project folder above to start the automated test
              pipeline. A saved reference only points to a project in this
              browser.
            </p>
          </div>
        ) : visibleProjects.length === 0 ? (
          <p className="text-sm text-slate-400">
            No projects match your search.
          </p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {visibleProjects.map((project) => {
              const rows = projectMetaRows(project)
              return (
                <li
                  key={project.id}
                  className="flex items-center justify-between gap-4 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-base font-medium">
                      {project.name}
                    </p>
                    {rows.length > 0 && (
                      <dl className="mt-1 space-y-0.5">
                        {rows.map((row) => (
                          <div key={row.label} className="flex gap-2 text-xs">
                            <dt className="text-slate-600">{row.label}</dt>
                            <dd className="text-slate-300">{row.value}</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                    <p className="mt-0.5 truncate font-mono text-xs text-slate-600">
                      {project.id}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <Link
                      to={`/projects/${encodeURIComponent(project.id)}`}
                      className="rounded-md bg-slate-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-600"
                    >
                      Open Project
                    </Link>
                    <button
                      type="button"
                      onClick={() => remove(project.id)}
                      aria-label={`Remove ${project.name} from this browser's saved list`}
                      title="Removes this saved reference. The backend project is not affected."
                      className="rounded-md px-2 py-1.5 text-sm text-slate-400 underline-offset-2 hover:text-slate-200 hover:underline"
                    >
                      Remove
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {confirmingClear && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="clear-list-dialog-title"
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              closeClearDialog()
            }
          }}
          className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/70 p-4"
        >
          <div className="w-full max-w-md rounded-lg border border-slate-700 bg-slate-900 p-5">
            <h3
              id="clear-list-dialog-title"
              className="text-base font-semibold text-white"
            >
              Clear the saved list?
            </h3>
            <p className="mt-2 text-sm text-slate-300">
              This removes the saved project references from this browser. It
              does not delete any backend projects — the projects themselves
              and their pipeline state are unaffected.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                ref={cancelClearRef}
                type="button"
                onClick={closeClearDialog}
                className="rounded-md border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                ref={confirmClearRef}
                type="button"
                onClick={() => {
                  clear()
                  closeClearDialog()
                }}
                className="rounded-md bg-red-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-600"
              >
                Clear saved list
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}