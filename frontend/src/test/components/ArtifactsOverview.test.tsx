import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ArtifactsOverview } from '../../components/ArtifactsOverview'
import { projectDetailsFixture } from '../mocks/handlers'

describe('ArtifactsOverview', () => {
  it('marks artifacts available only when the backend delivers them', () => {
    const project = projectDetailsFixture()
    render(<ArtifactsOverview project={project} />)

    expect(screen.getByText('Code map')).toBeDefined()
    expect(screen.getAllByText('Not available')).toHaveLength(4)
    expect(screen.getAllByText('Available')).toHaveLength(6)
  })

  it('shows a status chip from the artifact overall_status or status when present', () => {
    const project = projectDetailsFixture()
    render(<ArtifactsOverview project={project} />)
    expect(screen.getByText('failures_diagnosed')).toBeDefined()
    expect(screen.getByText('still_failing')).toBeDefined()
    expect(screen.getByText('validated_pending_approval')).toBeDefined()
  })

  it('renders every expected artifact label', () => {
    const project = projectDetailsFixture({})
    render(<ArtifactsOverview project={project} />)
    for (const label of [
      'Profile',
      'Code map',
      'Test plan',
      'Generated tests',
      'Test execution',
      'Diagnosis',
      'Improvement',
      'Re-test',
      'Evaluation',
      'Source repair',
    ]) {
      expect(screen.getByText(label)).toBeDefined()
    }
  })

  it('does not dump raw JSON into the overview', () => {
    const project = projectDetailsFixture()
    render(<ArtifactsOverview project={project} />)
    expect(screen.queryByText(/findings/)).toBeNull()
  })
})