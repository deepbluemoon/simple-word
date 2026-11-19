import test from 'node:test'
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { createServer } from 'node:net'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { readAws, readGcp } from '../src/clouds.mjs'

test('자격 증명이 없거나 SSH 호스트 형식이 잘못돼도 provider는 명확히 실패한다', async () => {
  await assert.rejects(readAws(''), /AWS_SSH_HOST/)
  await assert.rejects(readAws('host; rm -rf /'), /형식/)
  await assert.rejects(readGcp({ project: '' }), /GCP_PROJECT/)
})

test('서버는 루프백에서 응답하고 연결되지 않은 클라우드를 정상 응답으로 표시한다', async (t) => {
  const reservation = createServer()
  reservation.listen(0, '127.0.0.1')
  await once(reservation, 'listening')
  const port = reservation.address().port
  await new Promise((resolve, reject) => reservation.close((error) => error ? reject(error) : resolve()))

  const server = spawn(process.execPath, [fileURLToPath(new URL('../src/server.mjs', import.meta.url))], {
    cwd: path.resolve(new URL('..', import.meta.url).pathname),
    env: { ...process.env, OPS_DASHBOARD_PORT: String(port), AWS_SSH_HOST: '', GCP_PROJECT: '' },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  t.after(() => server.kill())
  await Promise.race([
    once(server.stdout, 'data'),
    once(server, 'exit').then(([code]) => { throw new Error(`server exited: ${code}`) }),
  ])
  const base = `http://127.0.0.1:${port}`
  const health = await fetch(`${base}/api/health`)
  assert.deepEqual(await health.json(), { ok: true, host: '127.0.0.1', port })
  const response = await fetch(`${base}/api/refresh`, { method: 'POST' })
  const clouds = await response.json()
  assert.equal(response.status, 200)
  assert.equal(clouds.aws.connected, false)
  assert.equal(clouds.gcp.connected, false)
  assert.match(clouds.aws.error, /AWS_SSH_HOST/)
  assert.match(clouds.gcp.error, /GCP_PROJECT/)
})
