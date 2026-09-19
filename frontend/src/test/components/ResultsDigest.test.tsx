import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import type { PropsWithChildren } from 'react'

import { ResultsDigest } from '../../components/ResultsDigest'
import { installMswServer } from '../mocks/install'
import { server } from '../mocks/server'

installMswServer()

beforeEach(() => {
  cleanup()
})

function renderDigest(projectId: string) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, retryDelay: 1 },
    },
  })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return render(<ResultsDigest projectId={projectId} />, { wrapper })
}

describe('ResultsDigest', () => {
  it('renders the failed verdict with reason', async () => {
    renderDigest('demo_project')
    expect(await screen.findByText('Failed')).toBeDefined()
    expect(screen.getByText('Test execution failed.')).toBeDefined()
  })

  it('renders execution counters', async () => {
    renderDigest('demo_project')
    await screen.findByText('Failed')
    expect(screen.getByText('Passed:')).toBeDefined()
    expect(screen.getByText('2')).toBeDefined()
    expect(screen.getByText('Tests:')).toBeDefined()
  })

  it('renders failing tests with normalized source locations', async () => {
    renderDigest('demo_project')
    await screen.findByText('Failed')
    expect(screen.getByText('test_add')).toBeDefined()
    expect(screen.getAllByText(/calculator\.py/).length).toBeGreaterThan(0)
    expect(screen.getByText('expected 4 got 5')).toBeDefined()
  })

  it('renders the repair section when repair evidence exists', async () => {
    renderDigest('demo_project')
    await screen.findByText('Failed')
    expect(screen.getByText('Repair target:')).toBeDefined()
    expect(screen.getByText('A validated candidate awaits explicit approval.')).toBeDefined()
  })

  it('renders the evaluation section when evaluation exists', async () => {
    renderDigest('demo_project')
    await screen.findByText('Failed')
    expect(screen.getByText('Line coverage:')).toBeDefined()
    expect(screen.getByText('66.7%')).toBeDefined()
    expect(screen.getByText('Mutation score:')).toBeDefined()
  })

  it('renders the passed verdict when repair was applied and validated', async () => {
    renderDigest('r_complete')
    expect(await screen.findByText('Passed')).toBeDefined()
    expect(
      screen.getByText('Source repair applied and final validation passed.'),
    ).toBeDefined()
    expect(screen.getByText('Final validation:')).toBeDefined()
  })

  it('renders empty-state sections for a project with no execution', async () => {
    renderDigest('r_partial')
    expect(await screen.findByText('No execution yet')).toBeDefined()
    expect(screen.queryByText('Passed:')).toBeNull()
    expect(screen.queryByText('Repair target:')).toBeNull()
    expect(screen.queryByText('Line coverage:')).toBeNull()
    expect(screen.queryByRole('region', { name: 'Execution' })).toBeNull()
    expect(screen.queryByRole('region', { name: 'Diagnosis' })).toBeNull()
  })

  it('exposes labelled regions for screen readers', async () => {
    renderDigest('demo_project')
    await screen.findByText('Failed')
    const regions = screen.getAllByRole('region')
    expect(regions.length).toBeGreaterThan(0)
  })

  it('shows a loading indicator before data arrives', () => {
    renderDigest('slow_results')
    expect(screen.getByText('Loading results summary…')).toBeDefined()
  })

  it('shows the not-available message for unknown projects (404)', async () => {
    renderDigest('missing')
    expect(
      await screen.findByText('Results are not available for this project.'),
    ).toBeDefined()
  })

  it('shows the server error state with a retry action', async () => {
    server.use(
      http.get('/api/projects/server_error/results', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderDigest('server_error')
    expect(await screen.findByText('Could not load results.')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeDefined()
  })

  it('recovers after retry when the error clears', async () => {
    let calls = 0
    server.use(
      http.get('/api/projects/flaky/results', () => {
        calls += 1
        if (calls <= 3) {
          return HttpResponse.json({ detail: 'boom' }, { status: 500 })
        }
        return HttpResponse.json({
          schema_version: 1,
          project_id: 'flaky',
          created_at: '2026-01-01T09:15:00Z',
          overall_verdict: 'no_execution',
          reason: 'No test execution has run yet.',
          pipeline_status: null,
          pipeline_current_stage: null,
          execution_status: null,
          execution_duration_seconds: null,
          test_counts: null,
          diagnosis_status: null,
          failing_tests: [],
          improvement_status: null,
          improvement_changes: null,
          improvement_files_modified: null,
          retest_status: null,
          repair: null,
          evaluation: null,
          warnings: [],
        })
      }),
    )
    renderDigest('flaky')
    expect(await screen.findByText('Could not load results.')).toBeDefined()
    screen.getByRole('button', { name: 'Retry' }).click()
    expect(await screen.findByText('No execution yet')).toBeDefined()
  })
})