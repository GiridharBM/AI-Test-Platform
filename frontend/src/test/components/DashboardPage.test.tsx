import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'

import App from '../../App'
import type { ProjectSummary } from '../../api/types'
import { registerLocalProject } from '../../registry/projects'
import { installMswServer } from '../mocks/install'
import { server } from '../mocks/server'

installMswServer()

function renderApp(initialPath = '/') {
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: {
              queries: { retry: false, refetchOnWindowFocus: false },
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

describe('DashboardPage', () => {
  it('renders the empty state when no projects are registered', () => {
    renderApp('/')
    expect(
      screen.getByRole('heading', { name: /dashboard/i }),
    ).toBeDefined()
    expect(screen.getByLabelText(/project folder/i)).toBeDefined()
    expect(
      screen.getByText(/no projects registered yet/i),
    ).toBeDefined()
  })

  it('lists registered projects and opens one from its workspace', () => {
    registerLocalProject({ id: 'aaa', name: 'Alpha Project' })
    registerLocalProject({ id: 'bbb', name: 'Beta Project' })

    renderApp('/')
    expect(screen.getByText('Alpha Project')).toBeDefined()
    expect(screen.getByText('Beta Project')).toBeDefined()

    const openButtons = screen.getAllByRole('link', { name: 'Open Project' })
    fireEvent.click(openButtons[0])

    expect(
      screen.getByRole('heading', { name: /project workspace/i }),
    ).toBeDefined()
    expect(screen.getByText('Project ID: bbb')).toBeDefined()
  })

  it('registers an uploaded project and navigates to its workspace', async () => {
    renderApp('/')

    const file = new File(['def add(): pass'], 'src/add.py')
    fireEvent.change(screen.getByLabelText(/project folder/i), {
      target: { files: [file] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }))

    expect(
      await screen.findByRole('heading', { name: /project workspace/i }),
    ).toBeDefined()
    expect(screen.getByText('Project ID: uploaded_abc123')).toBeDefined()
    expect(await screen.findByText('uploaded_abc123')).toBeDefined()
  })

  it('shows an error message when the upload is rejected', async () => {
    renderApp('/')

    const file = new File(['x'], 'server-error.txt')
    fireEvent.change(screen.getByLabelText(/project folder/i), {
      target: { files: [file] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/server error/i)
    expect(
      screen.getByRole('heading', { name: /dashboard/i }),
    ).toBeDefined()
  })

  it('filters the project list by case-insensitive name search', () => {
    registerLocalProject({ id: 'aaa', name: 'Alpha Project' })
    registerLocalProject({ id: 'bbb', name: 'Beta Project' })

    renderApp('/')
    expect(screen.getByText('Alpha Project')).toBeDefined()
    expect(screen.getByText('Beta Project')).toBeDefined()

    fireEvent.change(screen.getByLabelText('Search projects'), {
      target: { value: 'alpha' },
    })

    expect(screen.getByText('Alpha Project')).toBeDefined()
    expect(screen.queryByText('Beta Project')).toBeNull()
  })

  it('shows a no-results message when the search matches nothing', () => {
    registerLocalProject({ id: 'aaa', name: 'Alpha Project' })

    renderApp('/')
    fireEvent.change(screen.getByLabelText('Search projects'), {
      target: { value: 'zzz' },
    })

    expect(screen.queryByText('Alpha Project')).toBeNull()
    expect(
      screen.getByText(/no projects match your search/i),
    ).toBeDefined()
  })

  it('displays the recovered notice when the local registry has missing entries', () => {
    const raw = JSON.stringify([
      { id: 'aaa', name: 'Alpha' },
      'not-a-project',
    ])
    window.localStorage.setItem('auto-testing.projects', raw)

    renderApp('/')
    expect(
      screen.getByText(/saved project references could not be read/i),
    ).toBeDefined()
    expect(screen.getByText('Alpha')).toBeDefined()
  })

  it('allows removing a single saved project without reloading', () => {
    registerLocalProject({ id: 'aaa', name: 'Alpha Project' })
    registerLocalProject({ id: 'bbb', name: 'Beta Project' })

    renderApp('/')
    fireEvent.click(
      screen.getByRole('button', {
        name: /remove alpha project/i,
      }),
    )

    expect(screen.queryByText('Alpha Project')).toBeNull()
    expect(screen.getByText('Beta Project')).toBeDefined()
  })

  it('renders richer metadata on project cards', () => {
    registerLocalProject({
      id: 'abc',
      name: 'Calculator',
      createdAt: '2026-01-01T00:00:00Z',
      origin: 'upload',
      fileCount: 12,
      profiled: true,
    })

    renderApp('/')
    const card = within(
      screen.getByText('Calculator').closest('li') as HTMLElement,
    )
    expect(card.getByText('Origin')).toBeDefined()
    expect(card.getByText('Upload')).toBeDefined()
    expect(card.getByText('Files')).toBeDefined()
    expect(card.getByText('12')).toBeDefined()
    expect(card.getByText('Profile')).toBeDefined()
    expect(card.getByText('Profiled')).toBeDefined()
    expect(card.getByText('Added')).toBeDefined()
  })

  it('renders origin label mapped from the path origin', () => {
    registerLocalProject({ id: 'abc', name: 'ServerProject', origin: 'path' })
    renderApp('/')
    const card = within(
      screen.getByText('ServerProject').closest('li') as HTMLElement,
    )
    expect(card.getByText('Path')).toBeDefined()
    expect(card.getByText('Origin')).toBeDefined()
  })

  it('renders a zero file count truthfully', () => {
    registerLocalProject({ id: 'abc', name: 'EmptyDir', fileCount: 0 })
    renderApp('/')
    const card = within(
      screen.getByText('EmptyDir').closest('li') as HTMLElement,
    )
    expect(card.getByText('0')).toBeDefined()
    expect(card.getByText('Files')).toBeDefined()
  })

  it('renders Not profiled when profiled is false', () => {
    registerLocalProject({ id: 'abc', name: 'FreshProject', profiled: false })
    renderApp('/')
    const card = within(
      screen.getByText('FreshProject').closest('li') as HTMLElement,
    )
    expect(card.getByText('Not profiled')).toBeDefined()
  })

  it('falls back gracefully for an old-format entry without metadata', () => {
    registerLocalProject({ id: 'old', name: 'Legacy Project' })
    renderApp('/')
    expect(screen.getByText('Legacy Project')).toBeDefined()
    expect(screen.queryByText('Origin')).toBeNull()
    expect(screen.queryByText('Files')).toBeNull()
    expect(screen.queryByText('Profile')).toBeNull()
    expect(screen.queryByText('Added')).toBeNull()
  })

  it('renders safely when createdAt is invalid or missing', () => {
    registerLocalProject({ id: 'bad', name: 'Bad Date', createdAt: 'not-a-date' })
    registerLocalProject({ id: 'none', name: 'No Date' })

    renderApp('/')
    expect(screen.getByText('Bad Date')).toBeDefined()
    expect(screen.getByText('No Date')).toBeDefined()
    expect(screen.queryByText(/invalid/i)).toBeNull()
  })

  it('saves backend upload metadata into the local registry', async () => {
    renderApp('/')

    const file = new File(['def add(): pass'], 'src/add.py')
    fireEvent.change(screen.getByLabelText(/project folder/i), {
      target: { files: [file] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }))

    await screen.findByRole('heading', { name: /project workspace/i })
    const saved = JSON.parse(
      window.localStorage.getItem('auto-testing.projects') ?? '[]',
    )
    expect(saved[0]).toEqual({
      id: 'uploaded_abc123',
      name: 'uploaded-project',
      createdAt: '2026-01-01T10:00:00Z',
      origin: 'upload',
      fileCount: 1,
      profiled: false,
    })
  })

  it('does not create a registry entry when the upload fails', async () => {
    renderApp('/')

    const file = new File(['x'], 'server-error.txt')
    fireEvent.change(screen.getByLabelText(/project folder/i), {
      target: { files: [file] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/server error/i)
    expect(window.localStorage.getItem('auto-testing.projects')).toBeNull()
  })

  it('requires confirmation before clearing the saved list', () => {
    registerLocalProject({ id: 'aaa', name: 'Alpha Project' })

    renderApp('/')
    fireEvent.click(screen.getByRole('button', { name: 'Clear saved list' }))

    const dialog = screen.getByRole('dialog', {
      name: 'Clear the saved list?',
    })
    expect(dialog).toBeDefined()
    expect(
      screen.getByText(/does not delete any backend projects/i),
    ).toBeDefined()
    expect(screen.getByText('Alpha Project')).toBeDefined()
    expect(
      window.localStorage.getItem('auto-testing.projects'),
    ).not.toBeNull()
  })

  it('keeps the saved list when clearing is cancelled', () => {
    registerLocalProject({ id: 'aaa', name: 'Alpha Project' })

    renderApp('/')
    fireEvent.click(screen.getByRole('button', { name: 'Clear saved list' }))
    const dialog = screen.getByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByText('Alpha Project')).toBeDefined()
    expect(
      window.localStorage.getItem('auto-testing.projects'),
    ).not.toBeNull()
  })

  it('clears the local saved list only after confirmation', () => {
    registerLocalProject({ id: 'aaa', name: 'Alpha Project' })
    registerLocalProject({ id: 'bbb', name: 'Beta Project' })

    renderApp('/')
    fireEvent.click(screen.getByRole('button', { name: 'Clear saved list' }))
    const dialog = screen.getByRole('dialog')
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Clear saved list' }),
    )

    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.queryByText('Alpha Project')).toBeNull()
    expect(screen.queryByText('Beta Project')).toBeNull()
    expect(window.localStorage.getItem('auto-testing.projects')).toBeNull()
    expect(
      screen.getByText(/no projects registered yet/i),
    ).toBeDefined()
  })

  it('merges backend projects into the dashboard, backend metadata winning', async () => {
    registerLocalProject({
      id: 'p1',
      name: 'Stale Local Name',
      fileCount: 0,
      profiled: false,
    })
    server.use(
      http.get('/api/projects', () =>
        HttpResponse.json<ProjectSummary[]>([
          {
            project_id: 'p1',
            name: 'Fresh Server Name',
            origin: 'upload',
            file_count: 7,
            created_at: '2026-02-02T00:00:00Z',
            profiled: true,
          },
          {
            project_id: 'p2',
            name: 'Backend Only',
            origin: 'path',
            file_count: 2,
            created_at: '2026-03-01T00:00:00Z',
            profiled: false,
          },
        ]),
      ),
    )

    renderApp('/')
    expect(await screen.findByText('Fresh Server Name')).toBeDefined()
    expect(screen.getByText('Backend Only')).toBeDefined()
    expect(screen.getByText('7')).toBeDefined()
    expect(screen.queryByText('Stale Local Name')).toBeNull()

    const list = screen.getByRole('list')
    const names = Array.from(list.children).map((item) =>
      item.textContent ?? '',
    )
    expect(names[0]).toContain('Fresh Server Name')
    expect(names[1]).toContain('Backend Only')
  })

  it('falls back to the local-only list when the backend fetch fails', async () => {
    registerLocalProject({ id: 'aaa', name: 'Alpha Project' })
    server.use(
      http.get('/api/projects', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )

    renderApp('/')
    expect(await screen.findByText('Alpha Project')).toBeDefined()
    expect(screen.queryByText(/server error/i)).toBeNull()
  })
})

describe('ProjectWorkspacePage', () => {
  it('shows the project name from the local registry', () => {
    registerLocalProject({
      id: 'known-id',
      name: 'Known Project',
      createdAt: '2026-01-01T00:00:00Z',
    })

    render(
      <MemoryRouter initialEntries={['/projects/known-id']}>
        <QueryClientProvider
          client={
            new QueryClient({
              defaultOptions: { queries: { retry: false } },
            })
          }
        >
          <App />
        </QueryClientProvider>
      </MemoryRouter>,
    )

    expect(
      screen.getByRole('heading', { name: /project workspace/i }),
    ).toBeDefined()
    expect(screen.getByText('Known Project')).toBeDefined()
    expect(screen.getByText('Project ID: known-id')).toBeDefined()
  })
})