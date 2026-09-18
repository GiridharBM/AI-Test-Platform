import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { UploadProject } from '../../components/UploadProject'
import { installMswServer } from '../mocks/install'
import { server } from '../mocks/server'

installMswServer()

beforeEach(() => cleanup())

describe('UploadProject', () => {
  it('enables the upload button when files are selected', async () => {
    render(<UploadProject />)

    const input = screen.getByLabelText(/project folder/i)
    const button = screen.getByRole('button', { name: 'Upload' })

    expect(button).toBeDisabled()

    fireEvent.change(input, {
      target: { files: [new File(['def a(): pass'], 'a.py')] },
    })

    expect(button).not.toBeDisabled()
    expect(screen.getByText('1 file selected')).toBeDefined()
  })

  it('calls onUploaded on a successful upload', async () => {
    const onUploaded = vi.fn()
    render(<UploadProject onUploaded={onUploaded} />)

    const input = screen.getByLabelText(/project folder/i)
    const file = new File(['def a(): pass'], 'src/add.py')

    fireEvent.change(input, { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }))

    await waitFor(() => {
      expect(onUploaded).toHaveBeenCalledWith(
        expect.objectContaining({ project_id: 'uploaded_abc123' }),
      )
    })
  })

  it('displays a server error message when the upload fails', async () => {
    render(<UploadProject />)

    fireEvent.change(screen.getByLabelText(/project folder/i), {
      target: { files: [new File(['x'], 'server-error.txt')] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/server error/i)
  })

  it('does not report an upload failure when the onUploaded callback throws', async () => {
    const onUploaded = vi.fn(() => {
      throw new Error('registration failed')
    })
    render(<UploadProject onUploaded={onUploaded} />)

    fireEvent.change(screen.getByLabelText(/project folder/i), {
      target: { files: [new File(['x'], 'a.py')] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }))

    await waitFor(() => {
      expect(onUploaded).toHaveBeenCalledTimes(1)
    })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(
      screen.queryByRole('button', { name: 'Uploading…' }),
    ).toBeNull()
  })

  it('prevents a second submission while the upload is in progress', async () => {
    let release!: () => void
    server.use(
      http.post('/api/projects/upload', () =>
        new Promise<Response>((resolve) => {
          release = () =>
            resolve(
              HttpResponse.json({
                project_id: 'abc',
                name: 'p',
                origin: 'upload',
                source_path: null,
                file_count: 1,
                created_at: '2026-01-01T00:00:00Z',
                profiled: false,
              }),
            )
        }),
      ),
    )

    const onUploaded = vi.fn()
    render(<UploadProject onUploaded={onUploaded} />)

    const input = screen.getByLabelText(/project folder/i)
    const submit = () => fireEvent.click(screen.getByRole('button', { name: /upload/i }))

    fireEvent.change(input, {
      target: { files: [new File(['x'], 'a.py')] },
    })

    await act(async () => {
      submit()
    })

    const uploadingButton = await screen.findByRole('button', { name: 'Uploading…' })
    expect(uploadingButton).toBeDisabled()

    submit()

    await act(async () => {
      release()
    })

    await waitFor(() => {
      expect(onUploaded).toHaveBeenCalledTimes(1)
    })
  })
})