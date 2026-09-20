import { get, getBlob, postForm } from './client'
import type { BlobResult } from './client'
import type { PipelineState, ProjectDetails, ProjectMeta, ProjectSummary } from './types'

export const projectKeys = {
  all: ['projects'] as const,
  list: () => ['projects', 'list'] as const,
  detail: (projectId: string) => ['projects', 'detail', projectId] as const,
}

export function getProjects(): Promise<ProjectSummary[]> {
  return get<ProjectSummary[]>('/api/projects')
}

export function getProject(projectId: string): Promise<ProjectDetails> {
  return get<ProjectDetails>(`/api/projects/${encodeURIComponent(projectId)}`)
}

export function downloadProjectExport(projectId: string): Promise<BlobResult> {
  return getBlob(`/api/projects/${encodeURIComponent(projectId)}/export`)
}

export function getPipeline(projectId: string): Promise<PipelineState> {
  return get<PipelineState>(
    `/api/projects/${encodeURIComponent(projectId)}/pipeline`,
  )
}

export function uploadProject(files: File[]): Promise<ProjectMeta> {
  const formData = new FormData()
  for (const file of files) {
    const relativePath = file.webkitRelativePath || file.name
    formData.append('files', file, relativePath)
  }
  return postForm<ProjectMeta>('/api/projects/upload', formData)
}