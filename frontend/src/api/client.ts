type Json = unknown

export class ApiError extends Error {
  readonly status: number | null
  readonly detail: Json

  constructor(message: string, status: number | null, detail: Json) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }

  isConflict(): boolean {
    return this.status === 409
  }
}

export function apiErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return 'Unexpected error.'
  }
  if (error.status === null) {
    return 'Could not reach the server. Check that the backend is running.'
  }
  if (error.status >= 500) {
    return `Server error (${error.status}).`
  }
  return error.message
}

const JSON_HEADERS = { Accept: 'application/json' }

export function get<T>(path: string): Promise<T> {
  return request<T>(path, { headers: JSON_HEADERS })
}

export function post<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'POST', headers: JSON_HEADERS })
}

export function postForm<T>(path: string, formData: FormData): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: formData,
    headers: JSON_HEADERS,
  })
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch (err) {
    throw new ApiError(
      err instanceof Error ? err.message : 'Network error',
      null,
      undefined,
    )
  }

  let body: Json
  try {
    body = await parseJsonBody(res)
  } catch {
    throw new ApiError(
      `Unexpected response format (status ${res.status})`,
      res.status,
      undefined,
    )
  }

  if (!res.ok) {
    const message = messageFromDetail(body) ?? `Request failed with status ${res.status}`
    throw new ApiError(message, res.status, body)
  }

  return body as T
}

async function parseJsonBody(res: Response): Promise<Json> {
  const text = await res.text()
  if (text === '') {
    return null
  }
  return JSON.parse(text) as Json
}

function messageFromDetail(detail: Json): string | undefined {
  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail)) {
    const msg = (detail[0] as { msg?: unknown } | undefined)?.msg
    if (typeof msg === 'string') {
      return msg
    }
  }
  if (detail !== null && typeof detail === 'object') {
    const d = detail as { detail?: unknown; message?: unknown }
    if (typeof d.detail === 'string') {
      return d.detail
    }
    if (typeof d.message === 'string') {
      return d.message
    }
  }
  return undefined
}