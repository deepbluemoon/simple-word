import http from 'node:http'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { readAws, readGcp, readActualCosts } from './clouds.mjs'

const root = path.dirname(fileURLToPath(import.meta.url))
const publicDir = path.join(root, 'public')
const host = '127.0.0.1'
const port = Number(process.env.OPS_DASHBOARD_PORT || 9760)
const configuredFx = Number(process.env.USD_KRW || 1350)
const fx = Number.isFinite(configuredFx) && configuredFx > 0 ? configuredFx : 1350
const prices = JSON.parse(await fs.readFile(path.join(root, 'prices.json'), 'utf8'))
let snapshot = { updatedAt: null, aws: { connected: false, error: '확인 중', containers: [] }, gcp: { connected: false, error: '확인 중', services: [] } }

async function refresh() {
  const [aws, gcp] = await Promise.allSettled([readAws(), readGcp()])
  snapshot = {
    updatedAt: new Date().toISOString(),
    aws: aws.status === 'fulfilled' ? { connected: true, containers: aws.value } : { connected: false, error: aws.reason.message, containers: [] },
    gcp: gcp.status === 'fulfilled' ? { connected: true, services: gcp.value } : { connected: false, error: gcp.reason.message, services: [] },
  }
  return snapshot
}

const send = (res, status, body, type = 'application/json; charset=utf-8') => {
  res.writeHead(status, { 'content-type': type, 'cache-control': 'no-store' })
  res.end(type.startsWith('application/json') ? JSON.stringify(body) : body)
}

const server = http.createServer(async (req, res) => {
  const pathname = new URL(req.url || '/', `http://${host}`).pathname
  if (req.method === 'GET' && pathname === '/api/health') return send(res, 200, { ok: true, host, port })
  if (req.method === 'GET' && pathname === '/api/clouds') return send(res, 200, snapshot)
  if (req.method === 'POST' && pathname === '/api/refresh') return send(res, 200, await refresh())
  if (req.method === 'GET' && pathname === '/api/costs') {
    const actual = await Promise.all(['aws', 'gcp'].map(async (cloud) => {
      try { return [cloud, await readActualCosts(cloud)] } catch { return [cloud, null] }
    }))
    const costs = Object.fromEntries(actual)
    return send(res, 200, { currency: 'USD', usdKrw: fx, priceDate: prices.checkedAt, sources: prices.sources, estimates: prices.items, actual: costs })
  }
  const requested = pathname === '/' ? 'index.html' : pathname.slice(1)
  const target = path.resolve(publicDir, requested)
  if (!target.startsWith(`${publicDir}${path.sep}`)) return send(res, 403, { error: 'forbidden' })
  try {
    const body = await fs.readFile(target)
    const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' }
    return send(res, 200, body, types[path.extname(target)] || 'application/octet-stream')
  } catch {
    return send(res, 404, { error: 'not found' })
  }
})

server.listen(port, host, () => console.log(`Ops dashboard listening on http://${host}:${port}`))
void refresh()
setInterval(refresh, Math.max(15_000, Number(process.env.OPS_DASHBOARD_POLL_MS || 30_000))).unref()
