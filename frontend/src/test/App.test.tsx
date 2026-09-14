import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it } from 'vitest'

import App from '../App'

afterEach(() => cleanup())

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter initialEntries={['/']}>
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: {
              queries: { retry: false, refetchOnWindowFocus: false },
            },
          })
        }
      >
        {children}
      </QueryClientProvider>
    </MemoryRouter>
  )
}

describe('Application shell', () => {
  it('renders the application shell', () => {
    render(<App />, { wrapper })
    expect(screen.getByText('Auto Testing Platform')).toBeDefined()
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeDefined()
  })

  it('renders the dashboard route at /', () => {
    render(<App />, { wrapper })
    expect(screen.getByRole('heading', { name: /dashboard/i })).toBeDefined()
  })
})

describe('Router', () => {
  it('renders the project workspace and shows the project id', () => {
    render(<App />, {
      wrapper: ({ children }) => (
        <MemoryRouter initialEntries={['/projects/abc123']}>
          <QueryClientProvider
            client={
              new QueryClient({
                defaultOptions: {
                  queries: { retry: false, refetchOnWindowFocus: false },
                },
              })
            }
          >
            {children}
          </QueryClientProvider>
        </MemoryRouter>
      ),
    })
    expect(
      screen.getByRole('heading', { name: /project workspace/i }),
    ).toBeDefined()
    expect(screen.getByText('Project ID: abc123')).toBeDefined()
  })
})