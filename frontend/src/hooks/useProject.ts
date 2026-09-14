import { useQuery } from '@tanstack/react-query'

import { ApiError } from '../api/client'
import { getProject, projectKeys } from '../api/projects'
import type { ProjectDetails } from '../api/types'

export function shouldRetryRead(failureCount: number, error: unknown): boolean {
  if (failureCount >= 2) {
    return false
  }
  if (!(error instanceof ApiError)) {
    return false
  }
  if (error.status === null) {
    return true
  }
  return error.status >= 500
}

export function useProject(projectId: string) {
  return useQuery<ProjectDetails>({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => getProject(projectId),
    retry: shouldRetryRead,
    refetchOnWindowFocus: false,
  })
}