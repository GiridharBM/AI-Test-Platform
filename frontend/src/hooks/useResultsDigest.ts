import { useQuery } from '@tanstack/react-query'

import { getResults, resultsKeys } from '../api/results'
import type { ResultsDigest } from '../api/types'
import { shouldRetryRead } from './useProject'

export function useResultsDigest(projectId: string) {
  return useQuery<ResultsDigest>({
    queryKey: resultsKeys.digest(projectId),
    queryFn: () => getResults(projectId),
    retry: shouldRetryRead,
    refetchOnWindowFocus: false,
  })
}