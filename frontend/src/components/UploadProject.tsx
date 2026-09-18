import { useEffect, useRef, useState } from 'react'

import { ApiError } from '../api/client'
import { uploadProject } from '../api/projects'
import type { ProjectMeta } from '../api/types'

interface UploadProjectProps {
  onUploaded?: (project: ProjectMeta) => void
}

function toUploadErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === null) {
      return 'Could not reach the server. Make sure the backend is running.'
    }
    if (err.status === 413) {
      return `Upload rejected: ${err.message}`
    }
    if (err.status === 422) {
      return 'Upload rejected: the provided files are not valid.'
    }
    if (err.status >= 500) {
      return `Server error (${err.status}). Please try again later.`
    }
    return `Upload failed: ${err.message}`
  }
  return 'An unexpected error occurred during upload.'
}

export function UploadProject({ onUploaded }: UploadProjectProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const input = inputRef.current
    if (input !== null) {
      input.setAttribute('webkitdirectory', '')
      input.setAttribute('directory', '')
    }
  }, [])

  async function handleUpload(): Promise<void> {
    if (files.length === 0 || uploading) {
      return
    }
    setUploading(true)
    setError(null)
    let meta: ProjectMeta | null = null
    try {
      meta = await uploadProject(files)
    } catch (err) {
      setError(toUploadErrorMessage(err))
      setUploading(false)
      return
    }
    setFiles([])
    if (inputRef.current !== null) {
      inputRef.current.value = ''
    }
    setUploading(false)
    try {
      onUploaded?.(meta)
    } catch {
      /* no-op */
    }
  }

  return (
    <form
      className="rounded-lg border border-slate-800 bg-slate-900 p-4"
      aria-busy={uploading}
      onSubmit={(event) => {
        event.preventDefault()
        void handleUpload()
      }}
    >
      <label htmlFor="project-files" className="block text-sm font-medium">
        Project folder
      </label>
      <p className="mt-0.5 text-xs text-slate-400">
        Select the project folder or its files. Relative paths are preserved.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <input
          id="project-files"
          ref={inputRef}
          type="file"
          multiple
          disabled={uploading}
          onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
          className="block max-w-full text-sm"
        />
        <button
          type="submit"
          disabled={uploading || files.length === 0}
          aria-busy={uploading}
          className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {uploading ? 'Uploading…' : 'Upload'}
        </button>
      </div>
      {files.length > 0 && !uploading && (
        <p className="mt-2 text-sm text-slate-300">
          {files.length} file{files.length === 1 ? '' : 's'} selected
        </p>
      )}
      {error !== null && (
        <p role="alert" className="mt-2 text-sm text-red-400">
          {error}
        </p>
      )}
    </form>
  )
}