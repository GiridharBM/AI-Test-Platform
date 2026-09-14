import { useCallback, useState } from 'react'

import {
  clearLocalProjects,
  getLocalProjects,
  registerLocalProject,
  type LocalProject,
} from '../registry/projects'

export function useProjectRegistry() {
  const [projects, setProjects] = useState<LocalProject[]>(() => getLocalProjects())

  const register = useCallback(
    (project: { id: string; name: string; createdAt?: string }) => {
      setProjects(registerLocalProject(project))
    },
    [],
  )

  const clear = useCallback(() => {
    setProjects(clearLocalProjects())
  }, [])

  return { projects, register, clear }
}