import { useMutation, useQueryClient } from '@tanstack/react-query'

import { ApiError } from '../api/client'
import { pipelineKeys } from '../api/pipeline'
import { downloadProjectExport, projectKeys } from '../api/projects'

export function useProjectExport(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => downloadProjectExport(projectId),
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename ?? `${projectId}-export.zip`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    },
    onError: (error) => {
      if (error instanceof ApiError && error.isConflict()) {
        queryClient.invalidateQueries({
          queryKey: pipelineKeys.detail(projectId),
        })
        queryClient.invalidateQueries({
          queryKey: projectKeys.detail(projectId),
        })
      }
    },
  })
}