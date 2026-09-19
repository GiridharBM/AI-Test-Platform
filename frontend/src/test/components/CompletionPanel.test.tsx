import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PropsWithChildren } from 'react'

import { CompletionPanel } from '../../components/CompletionPanel'
import { projectDetailsFixture } from '../mocks/handlers'
import { installMswServer } from '../mocks/install'
import { server } from '../mocks/server'

installMswServer()

beforeEach(() => {
  cleanup()
  vi.restoreAllMocks()
  delete (URL as { createObjectURL?: unknown }).createObjectURL
  delete (URL as { revokeObjectURL?: unknown }).revokeObjectURL
})

function renderPanel(project: ReturnType<typeof projectDetailsFixture>) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return render(<CompletionPanel project={project} />, { wrapper })
}

function stubDownload() {
  Object.defineProperty(URL, 'createObjectURL', {
    writable: true,
    configurable: true,
    value: vi.fn().mockReturnValue('blob:fixture'),
  })
  Object.defineProperty(URL, 'revokeObjectURL', {
    writable: true,
    configurable: true,
    value: vi.fn(),
  })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
}

describe('CompletionPanel', () => {
  it('renders the Pipeline completed heading', () => {
    renderPanel(projectDetailsFixture())
    expect(screen.getByText('Pipeline completed')).toBeDefined()
  })

  it('does not render a bare Completed text node', () => {
    renderPanel(projectDetailsFixture())
    expect(screen.queryByText('Completed')).toBeNull()
  })

  it('does not render the word Success', () => {
    renderPanel(projectDetailsFixture())
    expect(screen.queryByText('Success')).toBeNull()
  })

  it('does not claim all tests passed', () => {
    renderPanel(projectDetailsFixture())
    expect(screen.queryByText(/all tests passed/i)).toBeNull()
  })

  it('shows pending approval when repair is validated but not yet approved', () => {
    renderPanel(
      projectDetailsFixture({
        repair: {
          ...projectDetailsFixture().repair!,
          approval_state: 'pending',
          application_state: 'not_applied',
          final_validation: { status: 'passed', execution_result: null, reason: '' },
        },
      }),
    )
    expect(
      screen.getByText(/awaiting approval/),
    ).toBeDefined()
  })

  it('shows repair validated when final validation passed', () => {
    renderPanel(
      projectDetailsFixture({
        repair: {
          ...projectDetailsFixture().repair!,
          final_validation: { status: 'passed', execution_result: null, reason: '' },
        },
      }),
    )
    expect(screen.getByText('Repair validated')).toBeDefined()
  })

  it('shows repair approved when approval_state is approved', () => {
    renderPanel(
      projectDetailsFixture({
        repair: {
          ...projectDetailsFixture().repair!,
          approval_state: 'approved',
        },
      }),
    )
    expect(screen.getByText('Repair approved')).toBeDefined()
  })

  it('shows applied repair wording for upload origin', () => {
    renderPanel(
      projectDetailsFixture({
        origin: 'upload',
        repair: {
          ...projectDetailsFixture().repair!,
          approval_state: 'approved',
          application_state: 'applied',
          final_validation: { status: 'passed', execution_result: null, reason: '' },
        },
      }),
    )
    expect(
      screen.getByText('Repair applied to the platform workspace copy.'),
    ).toBeDefined()
  })

  it('shows applied repair wording for path origin', () => {
    renderPanel(
      projectDetailsFixture({
        origin: 'path',
        repair: {
          ...projectDetailsFixture().repair!,
          approval_state: 'approved',
          application_state: 'applied',
          final_validation: { status: 'passed', execution_result: null, reason: '' },
        },
      }),
    )
    expect(
      screen.getByText('Repair applied to the project source.'),
    ).toBeDefined()
  })

  it('shows rejected repair wording', () => {
    renderPanel(
      projectDetailsFixture({
        repair: {
          ...projectDetailsFixture().repair!,
          approval_state: 'rejected',
        },
      }),
    )
    expect(
      screen.getByText('Repair was rejected and not applied.'),
    ).toBeDefined()
  })

  it('renders nothing when repair is null and the project is path-origin', () => {
    renderPanel(projectDetailsFixture({ repair: null, origin: 'path' }))
    expect(screen.getByText('Pipeline completed')).toBeDefined()
    expect(screen.queryByText(/repair/i)).toBeNull()
  })

  it('shows the download action only for upload-origin projects', () => {
    renderPanel(
      projectDetailsFixture({ origin: 'upload' }),
    )
    expect(screen.getByText(/download the repaired project/i)).toBeDefined()
    expect(
      screen.getByRole('button', { name: /download project export/i }),
    ).toBeDefined()
  })

  it('hides the download action for path-origin projects', () => {
    renderPanel(
      projectDetailsFixture({ origin: 'path' }),
    )
    expect(screen.queryByText(/download the repaired project/i)).toBeNull()
    expect(
      screen.queryByRole('button', { name: /download project export/i }),
    ).toBeNull()
  })

  it('disables the button and shows loading state while exporting', async () => {
    stubDownload()
    server.use(
      http.get('/api/projects/slow_export/export', async () => {
        await new Promise((resolve) => setTimeout(resolve, 250))
        return new HttpResponse(new Uint8Array([80, 75, 5, 6]).buffer, {
          headers: {
            'Content-Type': 'application/zip',
            'Content-Disposition': 'attachment; filename="slow_export-export.zip"',
          },
        })
      }),
    )
    renderPanel(projectDetailsFixture({ origin: 'upload', project_id: 'slow_export' }))
    const button = screen.getByRole('button', {
      name: /download project export/i,
    })

    fireEvent.click(button)

    const loading = await screen.findByRole('button', { name: /exporting/i })
    expect((loading as HTMLButtonElement).disabled).toBe(true)

    await screen.findByRole('button', { name: /download project export/i })
  })

  it('shows the export error message when the export fails', async () => {
    stubDownload()
    renderPanel(
      projectDetailsFixture({ origin: 'upload', project_id: 'not_completed' }),
    )
    const button = screen.getByRole('button', {
      name: /download project export/i,
    })

    fireEvent.click(button)

    expect(await screen.findByText(/export failed/i)).toBeDefined()
    expect(await screen.findByText(/overall_status/i)).toBeDefined()
  })
})