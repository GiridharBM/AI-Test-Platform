import { get } from './client'
import type { ResultsDigest } from './types'

export const resultsKeys = {
  digest: (projectId: string) => ['projects', 'results', projectId] as const,
}

export function getResults(projectId: string): Promise<ResultsDigest> {
  return get<ResultsDigest>(
    `/api/projects/${encodeURIComponent(projectId)}/results`,
  )
}