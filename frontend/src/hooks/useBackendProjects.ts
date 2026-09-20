import { useQuery } from '@tanstack/react-query'

import { getProjects, projectKeys } from '../api/projects'

export function useBackendProjects() {
  return useQuery({
    queryKey: projectKeys.list(),
    queryFn: getProjects,
  })
}