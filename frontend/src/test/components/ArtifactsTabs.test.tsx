import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { ArtifactsTabs } from '../../components/ArtifactsTabs'
import {
  projectDetailsFixture,
  codemapFixture,
  testPlanFixture,
  testGenerationFixture,
  improvementFixture,
  appliedRepairFixture,
} from '../mocks/handlers'

beforeEach(() => {
  cleanup()
})

describe('ArtifactsTabs', () => {
  it('renders the ArtifactsOverview at the top', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    expect(screen.getAllByText('Profile').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Source repair').length).toBeGreaterThan(0)
  })

  it('renders tabs only for artifacts that are present', () => {
    const project = projectDetailsFixture({
      codemap: null,
      test_plan: null,
      test_generation: null,
      improvement: null,
    })
    render(<ArtifactsTabs project={project} />)
    expect(screen.getByRole('tab', { name: 'Profile' })).toBeDefined()
    expect(screen.getByRole('tab', { name: 'Test execution' })).toBeDefined()
    expect(screen.getByRole('tab', { name: 'Diagnosis' })).toBeDefined()
    expect(screen.getByRole('tab', { name: 'Re-test' })).toBeDefined()
    expect(screen.getByRole('tab', { name: 'Evaluation' })).toBeDefined()
    expect(screen.getByRole('tab', { name: 'Source repair' })).toBeDefined()
    expect(screen.queryByRole('tab', { name: 'Code map' })).toBeNull()
    expect(screen.queryByRole('tab', { name: 'Test plan' })).toBeNull()
  })

  it('shows empty state when no artifacts exist', () => {
    const project = projectDetailsFixture({
      profile: null,
      codemap: null,
      test_plan: null,
      test_generation: null,
      execution: null,
      diagnosis: null,
      improvement: null,
      retest: null,
      evaluation: null,
      repair: null,
    })
    render(<ArtifactsTabs project={project} />)
    expect(screen.getByText('No artifacts available yet.')).toBeDefined()
  })

  it('sets up tablist, tab, and tabpanel roles', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    expect(screen.getByRole('tablist')).toBeDefined()
    expect(screen.getAllByRole('tab').length).toBeGreaterThan(0)
    expect(screen.getByRole('tabpanel')).toBeDefined()
  })

  it('marks the first available tab as selected by default', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    const firstTab = screen.getAllByRole('tab')[0]
    expect(firstTab.getAttribute('aria-selected')).toBe('true')
  })

  it('switches to a different tab on click', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    const executionTab = screen.getByRole('tab', { name: 'Test execution' })
    fireEvent.click(executionTab)
    expect(executionTab.getAttribute('aria-selected')).toBe('true')
    expect(screen.getByRole('tabpanel')).toBeDefined()
  })

  it('renders profile details in the profile tab', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Profile' }))
    expect(screen.getByText(/Python/)).toBeDefined()
    expect(screen.getByText(/Small/)).toBeDefined()
  })

  it('renders codemap details when available', () => {
    const project = projectDetailsFixture({ codemap: codemapFixture() })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Code map' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText(/Source modules/)).toBeDefined()
    expect(within(panel).getByText(/25/)).toBeDefined()
  })

  it('renders execution details when available', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Test execution' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText(/Passed/)).toBeDefined()
    expect(within(panel).getByText(/1\.20s/)).toBeDefined()
  })

  it('renders diagnosis details when available', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Diagnosis' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText(/Findings/)).toBeDefined()
    expect(within(panel).getByText(/test_add/)).toBeDefined()
  })

  it('renders retest details when available', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Re-test' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText(/Still failing/)).toBeDefined()
    expect(within(panel).getByText(/Selected/)).toBeDefined()
  })

  it('renders evaluation details when available', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Evaluation' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('Line coverage:')).toBeDefined()
    expect(within(panel).getByText('Mutation score:')).toBeDefined()
  })

  it('renders repair details when available', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Source repair' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('Status:')).toBeDefined()
    expect(within(panel).getByText('Approval:')).toBeDefined()
  })

  it('renders test_plan details when available', () => {
    const project = projectDetailsFixture({ test_plan: testPlanFixture() })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Test plan' }))
    expect(screen.getByText(/Total specs/)).toBeDefined()
  })

  it('renders test_generation details when available', () => {
    const project = projectDetailsFixture({
      test_generation: testGenerationFixture(),
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Generated tests' }))
    expect(screen.getByText(/Files generated/)).toBeDefined()
    expect(screen.getByText(/test_calculator\.py/)).toBeDefined()
  })

  it('renders improvement details when available', () => {
    const project = projectDetailsFixture({
      improvement: improvementFixture(),
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Improvement' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('Status:')).toBeDefined()
    expect(within(panel).getByText('Files modified:')).toBeDefined()
  })

  it('shows applied repair wording for upload origin only in repair tab', () => {
    const project = projectDetailsFixture({
      origin: 'upload',
      repair: appliedRepairFixture(),
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Source repair' }))
    const panel = screen.getByRole('tabpanel')
    expect(
      within(panel).getByText('Repair applied to the platform workspace copy.'),
    ).toBeDefined()
  })

  it('does not show upload-origin wording for path origin', () => {
    const project = projectDetailsFixture({
      origin: 'path',
      repair: appliedRepairFixture(),
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Source repair' }))
    const panel = screen.getByRole('tabpanel')
    expect(
      within(panel).queryByText('Repair applied to the platform workspace copy.'),
    ).toBeNull()
  })

  it('renders completed line coverage as a percentage', () => {
    const project = projectDetailsFixture({
      evaluation: {
        ...projectDetailsFixture().evaluation!,
        coverage: {
          ...projectDetailsFixture().evaluation!.coverage,
          status: 'completed',
          line_percentage: 82.36,
        },
      },
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Evaluation' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('Line coverage:')).toBeDefined()
    expect(within(panel).getByText('82.4%')).toBeDefined()
  })

  it('renders non-completed line coverage as an em dash', () => {
    const project = projectDetailsFixture({
      evaluation: {
        ...projectDetailsFixture().evaluation!,
        coverage: {
          ...projectDetailsFixture().evaluation!.coverage,
          status: 'not_run',
          line_percentage: 0,
        },
      },
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Evaluation' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('Line coverage:')).toBeDefined()
    expect(within(panel).getByText('—')).toBeDefined()
  })

  it('renders blocked coverage as an em dash', () => {
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
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Evaluation' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('—')).toBeDefined()
  })

  it('renders unavailable coverage as an em dash', () => {
    const project = projectDetailsFixture({
      evaluation: {
        ...projectDetailsFixture().evaluation!,
        coverage: {
          ...projectDetailsFixture().evaluation!.coverage,
          status: 'unavailable',
          line_percentage: 0,
        },
      },
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Evaluation' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('—')).toBeDefined()
  })

  it('renders error coverage as an em dash', () => {
    const project = projectDetailsFixture({
      evaluation: {
        ...projectDetailsFixture().evaluation!,
        coverage: {
          ...projectDetailsFixture().evaluation!.coverage,
          status: 'error',
          line_percentage: 0,
        },
      },
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Evaluation' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('—')).toBeDefined()
  })
})
