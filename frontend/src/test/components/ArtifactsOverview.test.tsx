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

  it('shows a concise summary line per available artifact', () => {
    const project = projectDetailsFixture()
    render(<ArtifactsOverview project={project} />)
    expect(screen.getByText(/Small · Python/)).toBeDefined()
    expect(screen.getByText(/failed · 0 passed · 1 failed/)).toBeDefined()
    expect(screen.getByText(/1 still failing \/ regression/)).toBeDefined()
    expect(screen.getByText(/66\.7% line coverage/)).toBeDefined()
    expect(screen.getByText(/awaiting approval/)).toBeDefined()
  })

  it('highlights failed execution and unresolved retest as errors', () => {
    const project = projectDetailsFixture()
    render(<ArtifactsOverview project={project} />)
    const execution = screen.getByText('Test execution').closest('li')
    expect(execution?.className).toContain('border-red-800/50')
    const retest = screen.getByText('Re-test').closest('li')
    expect(retest?.className).toContain('border-red-800/50')
  })

  it('shows coverage-awaiting and repair-awaiting states as warnings', () => {
    const project = projectDetailsFixture({
      evaluation: {
        ...projectDetailsFixture().evaluation!,
        coverage: {
          ...projectDetailsFixture().evaluation!.coverage,
          status: 'blocked',
          line_percentage: 0,
        },
      },
    })
    render(<ArtifactsOverview project={project} />)
    const evaluation = screen.getByText('Evaluation').closest('li')
    expect(evaluation?.className).toContain('border-amber-700/50')
    const repair = screen.getByText('Source repair').closest('li')
    expect(repair?.className).toContain('border-amber-700/50')
  })
})