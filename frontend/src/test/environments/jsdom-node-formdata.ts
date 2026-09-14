import { builtinEnvironments } from 'vitest/environments'
import type { Environment } from 'vitest'

const nodeFormData = globalThis.FormData
const nodeFile = globalThis.File
const nodeBlob = globalThis.Blob

export default {
  name: 'jsdom-with-node-formdata',
  transformMode: 'web',
  async setup(global, options) {
    const jsdomEnv = builtinEnvironments.jsdom
    if (jsdomEnv.setup === undefined) {
      throw new Error('vitest jsdom environment has no setup()')
    }
    const result = await jsdomEnv.setup(global, options)
    Object.defineProperties(global, {
      FormData: { value: nodeFormData, configurable: true, writable: true },
      File: { value: nodeFile, configurable: true, writable: true },
      Blob: { value: nodeBlob, configurable: true, writable: true },
    })
    return result
  },
} satisfies Environment