import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError } from '../api/client'
import { pipelineKeys, runPipelineAction } from '../api/pipeline'
import { getPipeline, projectKeys } from '../api/projects'
import { resultsKeys } from '../api/results'
import type { PipelineActionName, PipelineState } from '../api/types'
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

function pipelineRevision(state: PipelineState | undefined): string {
  if (state === undefined) {
    return ''
  }
  return [
    state.overall_status,
    state.current_stage,
    state.completed_stages.join(','),
    state.updated_at,
    state.current_improvement_round,
    state.stage_history.length,
  ].join('|')
}

export function usePipeline(projectId: string) {
  const queryClient = useQueryClient()
  const lastRevision = useRef('')
  const result = useQuery<PipelineState>({
    queryKey: pipelineKeys.detail(projectId),
    queryFn: () => getPipeline(projectId),
    refetchInterval: (query) => pipelinePollingIntervalMs(query.state.data),
    retry: shouldRetryRead,
    refetchOnWindowFocus: false,
  })

  useEffect(() => {
    const state = result.data
    if (state === undefined) {
      return
    }
    const revision = pipelineRevision(state)
    if (lastRevision.current !== '' && lastRevision.current !== revision) {
      queryClient.invalidateQueries({
        queryKey: resultsKeys.digest(projectId),
      })
      queryClient.invalidateQueries({
        queryKey: projectKeys.detail(projectId),
      })
    }
    lastRevision.current = revision
  }, [result.data, projectId, queryClient])

  return result
}

export function usePipelineAction(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation<PipelineState, unknown, PipelineActionName>({
    mutationFn: (action) => runPipelineAction(projectId, action),
    onSuccess: (data) => {
      queryClient.setQueryData(pipelineKeys.detail(projectId), data)
      queryClient.invalidateQueries({ queryKey: projectKeys.detail(projectId) })
      queryClient.invalidateQueries({ queryKey: resultsKeys.digest(projectId) })
    },
    onError: (error) => {
      if (error instanceof ApiError && error.isConflict()) {
        queryClient.invalidateQueries({ queryKey: pipelineKeys.detail(projectId) })
      }
    },
  })
}