import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { ProjectHeader } from '../../components/ProjectHeader'

function renderHeader(props: Parameters<typeof ProjectHeader>[0]) {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <ProjectHeader {...props} />
    </MemoryRouter>,
  )
}

describe('ProjectHeader', () => {
  it('renders the workspace heading and project ID', () => {
    renderHeader({ projectId: 'abc123' })
    expect(
      screen.getByRole('heading', { name: /project workspace/i }),
    ).toBeDefined()
    expect(screen.getByText('Project ID: abc123')).toBeDefined()
  })

  it('renders the authoritative project name when available', () => {
    renderHeader({ projectId: 'abc123', name: 'calculator' })
    expect(screen.getByText('calculator')).toBeDefined()
  })

  it('shows the registry fallback name with a hint while details load', () => {
    renderHeader({ projectId: 'abc123', fallbackName: 'Known Project' })
    expect(screen.getByText('Known Project')).toBeDefined()
    expect(
      screen.getByText(/from local registry/i),
    ).toBeDefined()
  })

  it('does not show the registry hint once authoritative data exists', () => {
    renderHeader({ projectId: 'abc123', name: 'calculator', fallbackName: 'Known' })
    expect(screen.getByText('calculator')).toBeDefined()
    expect(screen.queryByText(/from local registry/i)).toBeNull()
  })

  it('shows a loading message while details load without a name', () => {
    renderHeader({ projectId: 'abc123', loading: true })
    expect(screen.getByText('Loading project details…')).toBeDefined()
  })

  it('renders a back link to the dashboard', () => {
    renderHeader({ projectId: 'abc123' })
    expect(
      screen.getByRole('link', { name: /back to dashboard/i }),
    ).toHaveProperty('href', expect.stringMatching(/\/$/))
  })
})