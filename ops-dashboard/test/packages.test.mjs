import test from 'node:test'
import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { readPackageInventory } from '../src/packages.mjs'

test('Simple Word inventory reads the project manifests and resolved Python versions', async () => {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
  const inventory = await readPackageInventory(root, {
    installedVersions: { fastapi: '0.120.0', uvicorn: '0.38.0', pytest: '9.0.0', torch: '2.8.0' },
  })

  assert.deepEqual(inventory, [
    { ecosystem: 'PyPI', name: 'fastapi', version: '0.120.0', service: 'simple-word', scope: 'runtime' },
    { ecosystem: 'PyPI', name: 'uvicorn', version: '0.38.0', service: 'simple-word', scope: 'runtime' },
    { ecosystem: 'PyPI', name: 'pytest', version: '9.0.0', service: 'simple-word', scope: 'optional' },
    { ecosystem: 'PyPI', name: 'torch', version: '2.8.0', service: 'simple-word', scope: 'optional' },
  ])
})
