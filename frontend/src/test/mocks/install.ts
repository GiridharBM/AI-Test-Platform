import { afterAll, afterEach, beforeAll } from 'vitest'

import { server } from './server'

export function installMswServer() {
  beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
  afterEach(() => server.resetHandlers())
  afterAll(() => server.close())
}