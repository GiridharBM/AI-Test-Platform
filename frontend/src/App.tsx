import { Route, Routes } from 'react-router-dom'

import { Layout } from './components/Layout'
import { DashboardPage } from './pages/DashboardPage'
import { ProjectWorkspacePage } from './pages/ProjectWorkspacePage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/projects/:id" element={<ProjectWorkspacePage />} />
      </Route>
    </Routes>
  )
}