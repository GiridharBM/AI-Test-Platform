import { useCallback, useState } from 'react'

import {
  clearLocalProjects,
  readLocalProjects,
  registerLocalProject,
  removeLocalProject,
  type LocalProjectInput,
} from '../registry/projects'

export function useProjectRegistry() {
  const [state, setState] = useState(() => readLocalProjects())

  const register = useCallback(
    (project: LocalProjectInput) => {
      const next = registerLocalProject(project)
      setState({ ...state, projects: next })
    },
    [state],
  )

  const remove = useCallback((id: string) => {
    const next = removeLocalProject(id)
    setState({ ...state, projects: next })
  }, [state])

  const clear = useCallback(() => {
    clearLocalProjects()
    setState({ projects: [], recovered: false })
  }, [])

  return {
    projects: state.projects,
    recovered: state.recovered,
    register,
    remove,
    clear,
  }
}