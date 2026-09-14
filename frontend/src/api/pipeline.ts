import { post } from './client'
import type { PipelineState } from './types'

export const pipelineKeys = {
  detail: (projectId: string) => ['projects', projectId, 'pipeline'] as const,
}

function actionPath(projectId: string, action: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}/pipeline/${action}`
}

export function startPipeline(projectId: string): Promise<PipelineState> {
  return post<PipelineState>(actionPath(projectId, 'start'))
}

export function resumePipeline(projectId: string): Promise<PipelineState> {
  return post<PipelineState>(actionPath(projectId, 'resume'))
}

export function retestPipeline(projectId: string): Promise<PipelineState> {
  return post<PipelineState>(actionPath(projectId, 'retest'))
}

export function skipRetest(projectId: string): Promise<PipelineState> {
  return post<PipelineState>(actionPath(projectId, 'skip-retest'))
}

export function repairPipeline(projectId: string): Promise<PipelineState> {
  return post<PipelineState>(actionPath(projectId, 'repair'))
}

export function skipRepair(projectId: string): Promise<PipelineState> {
  return post<PipelineState>(actionPath(projectId, 'skip-repair'))
}

export function approveRepair(projectId: string): Promise<PipelineState> {
  return post<PipelineState>(actionPath(projectId, 'approve'))
}

export function rejectRepair(projectId: string): Promise<PipelineState> {
  return post<PipelineState>(actionPath(projectId, 'reject'))
}