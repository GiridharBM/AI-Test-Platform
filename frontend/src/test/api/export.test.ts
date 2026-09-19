import { describe, expect, it } from 'vitest'

import { ApiError, getBlob } from '../../api/client'
import { downloadProjectExport } from '../../api/projects'
import { EXPORT_ZIP_BYTES } from '../mocks/handlers'
import { installMswServer } from '../mocks/install'

installMswServer()

describe('getBlob', () => {
  it('returns the blob and filename on success', async () => {
    const { blob, filename } = await getBlob(
      '/api/projects/demo_project/export',
    )

    expect(blob).toBeInstanceOf(Blob)
    expect(blob.type).toBe('application/zip')
    expect(await blob.arrayBuffer()).toEqual(EXPORT_ZIP_BYTES.buffer)
    expect(filename).toBe('demo_project-export.zip')
  })

  it('rejects with ApiError status 409 and isConflict() true on conflict', async () => {
    const error = await getBlob('/api/projects/not_completed/export').then(
      () => null,
      (err: unknown) => err,
    )

    expect(error).toBeInstanceOf(ApiError)
    if (error instanceof ApiError) {
      expect(error.status).toBe(409)
      expect(error.isConflict()).toBe(true)
      expect(error.message).toContain("overall_status='completed'")
    }
  })

  it('rejects with ApiError status 404 when the project is missing', async () => {
    const error = await getBlob('/api/projects/missing/export').then(
      () => null,
      (err: unknown) => err,
    )

    expect(error).toBeInstanceOf(ApiError)
    if (error instanceof ApiError) {
      expect(error.status).toBe(404)
      expect(error.isConflict()).toBe(false)
    }
  })

  it('rejects with ApiError status 400 for path-origin projects', async () => {
    const error = await getBlob('/api/projects/path_origin/export').then(
      () => null,
      (err: unknown) => err,
    )

    expect(error).toBeInstanceOf(ApiError)
    if (error instanceof ApiError) {
      expect(error.status).toBe(400)
      expect(error.message).toContain('upload-origin')
    }
  })
})

describe('downloadProjectExport', () => {
  it('fetches the export endpoint for the project id', async () => {
    const { blob, filename } = await downloadProjectExport('demo_project')

    expect(blob.type).toBe('application/zip')
    expect(filename).toBe('demo_project-export.zip')
  })

  it('encodes the project id in the export path', async () => {
    const { filename } = await downloadProjectExport('my project')

    expect(filename).toBe('my project-export.zip')
  })
})