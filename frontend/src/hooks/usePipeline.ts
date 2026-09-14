import { useQuery } from '@tanstack/react-query'

import { getPipeline } from '../api/projects'
import { pipelineKeys } from '../api/pipeline'
import type { PipelineState } from '../api/types'
import { shouldRetryRead } from './useProject'

export const PIPELINE_POLL_RUNNING_MS = 2000
export const PIPELINE_POLL_WAITING_MS = 4000

export function pipelinePollingIntervalMs(
  state: PipelineState | undefined,
): number | false {
  if (state === undefined) {
    return false
  }
  switch (state.overall_status) {
    case 'running':
      return PIPELINE_POLL_RUNNING_MS
    case 'waiting_for_user':
    case 'waiting_for_approval':
      return PIPELINE_POLL_WAITING_MS
    default:
      return false
  }
}

export function usePipeline(projectId: string) {
  return useQuery<PipelineState>({
    queryKey: pipelineKeys.detail(projectId),
    queryFn: () => getPipeline(projectId),
    refetchInterval: (query) => pipelinePollingIntervalMs(query.state.data),
    retry: shouldRetryRead,
    refetchOnWindowFocus: false,
  })
}