import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import App from '../../App'
import { registerLocalProject } from '../../registry/projects'
import { pipelineFixture, projectDetailsFixture } from '../mocks/handlers'
import { installMswServer } from '../mocks/install'
import { server } from '../mocks/server'

installMswServer()

function renderWorkspace(projectId: string) {
  render(
    <MemoryRouter initialEntries={[`/projects/${projectId}`]}>
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: {
              queries: {
                retry: false,
                retryDelay: 0,
                refetchOnWindowFocus: false,
              },
            },
          })
        }
      >
        <App />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
  cleanup()
})

describe('Project workspace — loading and project details', () => {
  it('renders a project loading state', () => {
    renderWorkspace('p_completed')
    expect(
      screen.getAllByText('Loading project details…').length,
    ).toBeGreaterThan(0)
  })

  it('renders project details after a successful response', async () => {
    renderWorkspace('p_completed')
    expect(await screen.findByText('p_completed')).toBeDefined()
    expect(
      (await screen.findAllByText('(completed)')).length,
    ).toBeGreaterThan(0)
  })

  it('displays the project ID', async () => {
    renderWorkspace('p_completed')
    expect(await screen.findByText('Project ID: p_completed')).toBeDefined()
  })

  it('displays the project name from authoritative data', async () => {
    renderWorkspace('p_completed')
    expect(await screen.findByText('p_completed')).toBeDefined()
  })

  it('navigates back to the dashboard', async () => {
    renderWorkspace('p_completed')
    const back = await screen.findByRole('link', { name: /back to dashboard/i })
    fireEvent.click(back)
    expect(
      await screen.findByRole('heading', { name: /dashboard/i }),
    ).toBeDefined()
  })
})

describe('Project workspace — pipeline states', () => {
  it('renders a pipeline loading state', () => {
    renderWorkspace('p_completed')
    expect(screen.getByText('Loading pipeline state…')).toBeDefined()
  })

  it('renders the current stage', async () => {
    renderWorkspace('p_waiting_user')
    expect(await screen.findByText('(awaiting_retest_decision)')).toBeDefined()
  })

  it('renders the overall status', async () => {
    renderWorkspace('p_waiting_user')
    expect(await screen.findByText('(waiting_for_user)')).toBeDefined()
  })

  it('renders completed stages from the backend list', async () => {
    renderWorkspace('p_waiting_user')
    await screen.findByText('(waiting_for_user)')
    const doneSteps = screen.getAllByLabelText(/: done/)
    expect(doneSteps.map((el) => el.getAttribute('aria-label'))).toEqual(
      expect.arrayContaining([
        'Profile: done',
        'Discover: done',
        'Plan: done',
        'Generate: done',
        'Execute: done',
        'Diagnose: done',
        'Improve: done',
        'Re-test: done',
      ]),
    )
  })

  it('renders stage history records', async () => {
    renderWorkspace('p_completed')
    await screen.findAllByText('(completed)')
    expect(screen.getAllByText('Success')).toHaveLength(8)
  })

  it('renders the improvement round when present', async () => {
    renderWorkspace('p_waiting_user')
    expect(
      await screen.findByText('Improvement round 3 of 3'),
    ).toBeDefined()
  })

  it('renders the pipeline reason', async () => {
    renderWorkspace('p_completed')
    expect(
      await screen.findByText('Pipeline completed successfully.'),
    ).toBeDefined()
  })

  it('renders warnings distinctly from fatal errors', async () => {
    renderWorkspace('p_blocked')
    expect(
      (await screen.findAllByText('Docker runtime unavailable.')).length,
    ).toBeGreaterThan(0)
    expect(screen.queryByText('Error')).toBeNull()
  })

  it('renders a terminal completed state', async () => {
    renderWorkspace('p_completed')
    expect(await screen.findByText('Completed')).toBeDefined()
    expect(screen.queryByLabelText(/in progress/)).toBeNull()
  })

  it('renders a failed state', async () => {
    renderWorkspace('p_failed')
    expect(
      (await screen.findAllByText('(failed)')).length,
    ).toBeGreaterThan(0)
    expect(
      await screen.findByText('Test execution failed: 3 of 2 tests failed.'),
    ).toBeDefined()
    expect(screen.getAllByText('Failed').length).toBeGreaterThan(0)
  })

  it('renders a blocked state', async () => {
    renderWorkspace('p_blocked')
    expect(await screen.findByText('(blocked)')).toBeDefined()
  })

  it('renders an unavailable state', async () => {
    renderWorkspace('p_unavailable')
    expect(await screen.findByText('(unavailable)')).toBeDefined()
    expect(
      await screen.findByText('Model provider API is unreachable.'),
    ).toBeDefined()
  })

  it('renders a rejected state', async () => {
    renderWorkspace('p_rejected')
    expect(await screen.findByText('(rejected)')).toBeDefined()
    expect(
      await screen.findByText('Reason: User rejected the repair candidate.'),
    ).toBeDefined()
  })
})

describe('Project workspace — pipeline 404', () => {
  it('shows that pipeline state is not available yet', async () => {
    renderWorkspace('no_pipeline')
    expect(
      await screen.findByText(/Pipeline state is not available yet/),
    ).toBeDefined()
    expect(screen.queryByText('(waiting_for_user)')).toBeNull()
  })
})

describe('Project workspace — errors', () => {
  it('renders a project-not-found state with a way back', async () => {
    renderWorkspace('missing')
    expect(await screen.findByText('Project not found.')).toBeDefined()
    expect(
      screen.getAllByRole('link', { name: /back to dashboard/i }).length,
    ).toBeGreaterThan(0)
  })

  it('shows a useful server error for a failed project read', async () => {
    server.use(
      http.get('/api/projects/p500', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderWorkspace('p500')
    expect(
      await screen.findByText(/Could not open this project/i),
    ).toBeDefined()
    expect(screen.getByText(/Server error \(500\)/)).toBeDefined()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeDefined()
    expect(
      screen.getAllByRole('link', { name: /back to dashboard/i }).length,
    ).toBeGreaterThan(0)
  })

  it('shows a truthful panel for network failures distinct from a 404', async () => {
    server.use(
      http.get('/api/projects/net_proj/pipeline', () =>
        HttpResponse.error(),
      ),
      http.get('/api/projects/net_proj', () => HttpResponse.error()),
    )
    renderWorkspace('net_proj')
    expect(
      await screen.findByText(/Could not open this project/i),
    ).toBeDefined()
    expect(screen.queryByText('Project not found.')).toBeNull()
    expect(
      screen.getByText(/connection or server problem/i),
    ).toBeDefined()
  })

  it('allows removing a stale saved reference from the not-found panel', async () => {
    registerLocalProject({ id: 'missing', name: 'Stale Project' })
    renderWorkspace('missing')
    expect(await screen.findByText('Project not found.')).toBeDefined()

    fireEvent.click(
      screen.getByRole('button', { name: /remove saved reference/i }),
    )

    expect(
      await screen.findByRole('heading', { name: /dashboard/i }),
    ).toBeDefined()
    expect(screen.queryByText('Stale Project')).toBeNull()
  })

  it('preserves a 409 conflict as an error, not a success', async () => {
    renderWorkspace('conflict')
    expect(
      await screen.findByText(/Could not load pipeline state/),
    ).toBeDefined()
    expect(
      await screen.findByText(/Invalid pipeline gate/),
    ).toBeDefined()
    expect(screen.queryByText('(waiting_for_user)')).toBeNull()
    expect(screen.getByText('No stage history recorded yet.')).toBeDefined()
  })

  it('renders a useful server error for pipeline reads', async () => {
    server.use(
      http.get('/api/projects/explode/pipeline', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderWorkspace('explode')
    expect(
      await screen.findByText(/Could not load pipeline state/),
    ).toBeDefined()
    expect(await screen.findByText(/Server error \(500\)/)).toBeDefined()
  })

  it('renders a useful message for failed network reads', async () => {
    server.use(
      http.get('/api/projects/net_fail/pipeline', () =>
        HttpResponse.error(),
      ),
    )
    renderWorkspace('net_fail')
    expect(
      await screen.findByText(/Could not reach the server/),
    ).toBeDefined()
  })

  it('retries the pipeline read and shows data after it succeeds', async () => {
    let fail = true
    server.use(
      http.get('/api/projects/retry_demo/pipeline', () => {
        if (fail) {
          return HttpResponse.json({ detail: 'transient' }, { status: 500 })
        }
        return HttpResponse.json(
          pipelineFixture('completed', { project_id: 'retry_demo' }),
        )
      }),
    )
    renderWorkspace('retry_demo')
    expect(
      await screen.findByText(/Could not load pipeline state/),
    ).toBeDefined()

    fail = false
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(
      (await screen.findAllByText('(completed)')).length,
    ).toBeGreaterThan(0)
  })
})

describe('Project workspace — decision gates', () => {
  it('renders decision buttons only when required', async () => {
    renderWorkspace('p_waiting_user')
    expect(
      await screen.findByRole('button', { name: 'Run re-test' }),
    ).toBeDefined()
    expect(
      screen.getByRole('button', { name: 'Skip re-test' }),
    ).toBeDefined()
  })

  it('advances past the retest gate after acting', async () => {
    renderWorkspace('p_waiting_user')
    fireEvent.click(
      await screen.findByRole('button', { name: 'Run re-test' }),
    )
    expect(
      await screen.findByRole('button', { name: 'Run repair' }),
    ).toBeDefined()
    expect(
      screen.queryByRole('button', { name: 'Run re-test' }),
    ).toBeNull()
  })

  it('does not render decision buttons at non-gate states', async () => {
    renderWorkspace('p_completed')
    await screen.findByText('p_completed')
    expect(screen.queryByRole('button', { name: 'Run re-test' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Approve and apply repair' })).toBeNull()
  })

  it('reconciles immediately with authoritative state after a 409 conflict', async () => {
    let gets = 0
    let release!: (value: Response) => void
    server.use(
      http.post('/api/projects/p_waiting_user/pipeline/retest', () =>
        HttpResponse.json(
          {
            detail:
              'Invalid pipeline gate: action retest not permitted at awaiting_repair_approval',
          },
          { status: 409 },
        ),
      ),
      http.get('/api/projects/p_waiting_user/pipeline', () => {
        gets += 1
        if (gets > 1) {
          return new Promise<Response>((resolve) => {
            release = resolve
          })
        }
        return HttpResponse.json(
          pipelineFixture('waiting_for_user', {
            project_id: 'p_waiting_user',
            pipeline_id: 'p_waiting_user',
          }),
        )
      }),
    )
    renderWorkspace('p_waiting_user')
    fireEvent.click(
      await screen.findByRole('button', { name: 'Run re-test' }),
    )

    expect(await screen.findByRole('alert')).toBeDefined()

    release(
      HttpResponse.json(
        pipelineFixture('completed', {
          project_id: 'p_waiting_user',
          pipeline_id: 'p_waiting_user',
        }),
      ),
    )
    await waitFor(() => {
      expect(gets).toBeGreaterThan(1)
      expect(
        screen.queryByRole('button', { name: 'Run re-test' }),
      ).toBeNull()
      expect(
        screen.queryByRole('button', { name: 'Skip re-test' }),
      ).toBeNull()
})
})

describe('Project workspace — artifact navigation', () => {
  it('does not fetch project details again when switching artifact tabs', async () => {
    let projectGets = 0
    server.use(
      http.get('/api/projects/p_completed', () => {
        projectGets += 1
        return HttpResponse.json(
          projectDetailsFixture({
            project_id: 'p_completed',
            name: 'p_completed',
          }),
        )
      }),
    )
    renderWorkspace('p_completed')
    const profileTab = await screen.findByRole('tab', { name: 'Profile' })
    fireEvent.click(profileTab)
    const projectRequestsAfterLoad = projectGets
    fireEvent.click(screen.getByRole('tab', { name: 'Test execution' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Diagnosis' }))
    expect(projectGets).toBe(projectRequestsAfterLoad)
  })

  it('renders the artifacts section before the stage history', async () => {
    renderWorkspace('p_completed')
    const artifacts = await screen.findByRole('region', { name: 'Artifacts' })
    const history = await screen.findByRole('region', {
      name: 'Stage history',
    })
    expect(
      artifacts.compareDocumentPosition(history) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })
})

describe('Project workspace — results digest', () => {
  it('renders the Results section above the Artifacts section', async () => {
    renderWorkspace('p_completed')
    const results = await screen.findByRole('region', { name: 'Results' })
    const artifacts = await screen.findByRole('region', { name: 'Artifacts' })
    expect(
      results.compareDocumentPosition(artifacts) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it('renders the digest verdict without duplicating full artifact contents', async () => {
    renderWorkspace('r_complete')
    await screen.findByText('Passed')
    expect(screen.getByText('Source repair applied and final validation passed.')).toBeDefined()
    expect(screen.getAllByRole('region', { name: 'Execution' }).length).toBe(1)
  })

  it('omits sections for artifacts that do not exist (explicit unavailable)', async () => {
    renderWorkspace('r_partial')
    await screen.findByText('No execution yet')
    expect(screen.queryByRole('region', { name: 'Diagnosis' })).toBeNull()
    expect(screen.queryByRole('region', { name: 'Execution' })).toBeNull()
    expect(screen.queryByText('Repair target:')).toBeNull()
  })

  it('shows the error state for a results fetch failure', async () => {
    server.use(
      http.get('/api/projects/boom/results', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderWorkspace('boom')
    expect(await screen.findByText('Could not load results.')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeDefined()
  })
})
})