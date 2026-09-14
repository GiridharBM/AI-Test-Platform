import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { ApiError } from '../../api/client'
import { uploadProject } from '../../api/projects'
import { installMswServer } from '../mocks/install'
import { server } from '../mocks/server'

installMswServer()

describe('uploadProject', () => {
  it('POSTs multipart form-data to /api/projects/upload using the files field', async () => {
    let captured: FormData | undefined

    server.use(
      http.post('/api/projects/upload', async ({ request }) => {
        captured = await request.formData()
        return HttpResponse.json({
          project_id: 'uploaded_abc123',
          name: 'my-project',
          origin: 'upload',
          source_path: null,
          file_count: 2,
          created_at: '2026-01-01T10:00:00Z',
          profiled: false,
        })
      }),
    )

    const src = new File(['def add(a, b): return a + b'], 'src/add.py')
    const test = new File(['def test_add(): pass'], 'src/test_add.py')
    const meta = await uploadProject([src, test])

    const files = captured?.getAll('files') ?? []
    expect(files).toHaveLength(2)
    expect((files[0] as File).name).toBe('src/add.py')
    expect((files[1] as File).name).toBe('src/test_add.py')
    expect(captured?.getAll('paths')).toHaveLength(0)

    expect(meta.project_id).toBe('uploaded_abc123')
    expect(meta.name).toBe('my-project')
    expect(meta.origin).toBe('upload')
    expect(meta.file_count).toBe(2)
  })

  it('rejects with ApiError status 500 on a server error', async () => {
    server.use(
      http.post('/api/projects/upload', () =>
        HttpResponse.json({ detail: 'Internal server error during upload.' }, { status: 500 }),
      ),
    )

    const error = await uploadProject([new File(['x'], 'a.py')]).then(
      () => null,
      (err: unknown) => err,
    )

    expect(error).toBeInstanceOf(ApiError)
    if (error instanceof ApiError) {
      expect(error.status).toBe(500)
      expect(error.isConflict()).toBe(false)
    }
  })
})