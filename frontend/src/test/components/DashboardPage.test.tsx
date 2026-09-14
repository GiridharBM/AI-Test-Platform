import {
  cleanup,
  fireEvent,
  render,
  screen,
} from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import App from '../../App'
import { registerLocalProject } from '../../registry/projects'
import { installMswServer } from '../mocks/install'

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