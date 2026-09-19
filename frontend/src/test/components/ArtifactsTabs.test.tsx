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
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText(/Python/)).toBeDefined()
    expect(within(panel).getByText(/Small/)).toBeDefined()
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

  it('renders per-test rows with statuses when structured data exists', () => {
    const project = projectDetailsFixture({
      execution: {
        ...projectDetailsFixture().execution!,
        file_results: [
          {
            file_path: 'generated_tests/test_calculator.py',
            status: 'failed',
            stdout: '',
            stderr: '',
            duration_seconds: 1.2,
            test_functions: [
              { test_function: 'test_add', status: 'passed', duration_seconds: null },
              { test_function: 'test_div', status: 'failed', duration_seconds: null },
              { test_function: 'test_skip', status: 'skipped', duration_seconds: null },
            ],
          },
        ],
      },
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Test execution' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('test_add')).toBeDefined()
    expect(within(panel).getByText('test_div')).toBeDefined()
    expect(within(panel).getByText('test_skip')).toBeDefined()
    expect(within(panel).getAllByText('passed').length).toBeGreaterThan(0)
    expect(within(panel).getByText('skipped')).toBeDefined()
  })

  it('shows duration only when actually available per test', () => {
    const project = projectDetailsFixture({
      execution: {
        ...projectDetailsFixture().execution!,
        file_results: [
          {
            file_path: 'generated_tests/test_calculator.py',
            status: 'passed',
            stdout: '',
            stderr: '',
            duration_seconds: 1.2,
            test_functions: [
              { test_function: 'test_fast', status: 'passed', duration_seconds: 0.012 },
              { test_function: 'test_unknown', status: 'passed', duration_seconds: null },
            ],
          },
        ],
      },
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Test execution' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('0.012s')).toBeDefined()
    expect(within(panel).queryByText(/^nulls/)).toBeNull()
  })

  it('gracefully handles old execution artifacts without per-test rows', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Test execution' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText(/test_calculator\.py/)).toBeDefined()
    expect(within(panel).getByText('No per-test detail available for this file.')).toBeDefined()
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

  it('moves focus and selection with the right arrow key', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    const profileTab = screen.getByRole('tab', { name: 'Profile' })
    profileTab.focus()
    fireEvent.keyDown(profileTab, { key: 'ArrowRight' })
    const executionTab = screen.getByRole('tab', { name: 'Test execution' })
    expect(executionTab).toHaveFocus()
    expect(executionTab.getAttribute('aria-selected')).toBe('true')
    expect(profileTab.getAttribute('aria-selected')).toBe('false')
  })

  it('moves selection with the left arrow key and wraps around', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    const profileTab = screen.getByRole('tab', { name: 'Profile' })
    profileTab.focus()
    fireEvent.keyDown(profileTab, { key: 'ArrowLeft' })
    const repairTab = screen.getByRole('tab', { name: 'Source repair' })
    expect(repairTab).toHaveFocus()
    expect(repairTab.getAttribute('aria-selected')).toBe('true')
  })

  it('jumps to the first and last tab with Home and End keys', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    const diagnosisTab = screen.getByRole('tab', { name: 'Diagnosis' })
    diagnosisTab.focus()
    fireEvent.keyDown(diagnosisTab, { key: 'Home' })
    expect(screen.getByRole('tab', { name: 'Profile' })).toHaveFocus()
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Profile' }), {
      key: 'End',
    })
    expect(screen.getByRole('tab', { name: 'Source repair' })).toHaveFocus()
  })

  it('associates tabs with the panel via aria-controls and id', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    const panel = screen.getByRole('tabpanel')
    expect(panel.getAttribute('id')).toBe('artifact-tabpanel')
    expect(panel.getAttribute('aria-labelledby')).toBe('artifact-tab-profile')
    const profileTab = screen.getByRole('tab', { name: 'Profile' })
    expect(profileTab.getAttribute('aria-controls')).toBe('artifact-tabpanel')
    expect(profileTab.getAttribute('id')).toBe('artifact-tab-profile')
  })

  it('shows the generated test file content in a collapsible block', () => {
    const project = projectDetailsFixture({
      test_generation: testGenerationFixture(),
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Generated tests' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText(/test_calculator\.py/)).toBeDefined()
    const details = within(panel).getByText(/test_calculator\.py/).closest('details')
    expect(details).not.toBeNull()
    expect(within(details as HTMLElement).getByText(/assert add\(1, 2\) == 3/)).toBeDefined()
  })

  it('shows diagnosis traceback and exception in a collapsible finding', () => {
    const diagnosis = projectDetailsFixture().diagnosis!
    const project = projectDetailsFixture({
      diagnosis: {
        ...diagnosis,
        findings: [
          {
            ...diagnosis.findings[0],
            traceback: 'Traceback (most recent call last):\n  assert add(1, 2) == 3',
          },
        ],
      },
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Diagnosis' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText(/test_add/)).toBeDefined()
    const finding = within(panel).getByText(/test_add/).closest('details')
    expect(finding).not.toBeNull()
    const findingPanel = within(finding as HTMLElement)
    expect(findingPanel.getByText(/most recent call last/)).toBeDefined()
    expect(findingPanel.getByText(/AssertionError/)).toBeDefined()
  })

  it('shows improvement before and after code in a collapsible change', () => {
    const project = projectDetailsFixture({
      improvement: improvementFixture(),
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Improvement' }))
    const panel = screen.getByRole('tabpanel')
    const change = within(panel).getByText(/test_add/).closest('details')
    expect(change).not.toBeNull()
    const changePanel = within(change as HTMLElement)
    expect(changePanel.getByText(/assert add\(1, 2\) == 5/)).toBeDefined()
    expect(changePanel.getByText(/assert add\(1, 2\) == 3/)).toBeDefined()
  })

  it('shows repair candidate details and awaiting-approval wording', () => {
    render(<ArtifactsTabs project={projectDetailsFixture()} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Source repair' }))
    const panel = screen.getByRole('tabpanel')
    expect(
      within(panel).getByText(
        'Repair candidate validated and awaiting approval.',
      ),
    ).toBeDefined()
    const candidate = within(panel).getByText(/Candidate: replace binop body/).closest('details')
    expect(candidate).not.toBeNull()
    const candidatePanel = within(candidate as HTMLElement)
    expect(candidatePanel.getByText(/return a \+ b/)).toBeDefined()
    expect(within(panel).getByText(/Attempt 1/)).toBeDefined()
  })

  it('shows rejected repair wording', () => {
    const project = projectDetailsFixture({
      repair: {
        ...projectDetailsFixture().repair!,
        status: 'rejected',
        approval_state: 'rejected',
        application_state: 'not_applied',
      },
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Source repair' }))
    const panel = screen.getByRole('tabpanel')
    expect(
      within(panel).getByText('Repair was rejected and not applied.'),
    ).toBeDefined()
  })

  it('shows applied repair wording for path origin', () => {
    const project = projectDetailsFixture({
      origin: 'path',
      repair: appliedRepairFixture(),
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Source repair' }))
    const panel = screen.getByRole('tabpanel')
    expect(
      within(panel).getByText('Repair applied to the project source.'),
    ).toBeDefined()
  })

  it('shows final validation status when it ran', () => {
    const project = projectDetailsFixture({
      repair: {
        ...projectDetailsFixture().repair!,
        final_validation: {
          status: 'passed',
          execution_result: null,
          reason: 'All target tests pass after the repair.',
        },
      },
    })
    render(<ArtifactsTabs project={project} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Source repair' }))
    const panel = screen.getByRole('tabpanel')
    expect(within(panel).getByText('Final validation:')).toBeDefined()
    expect(
      within(panel).getByText('All target tests pass after the repair.'),
    ).toBeDefined()
  })
})
