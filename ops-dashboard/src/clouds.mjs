import { execFile } from 'node:child_process'
import { promisify } from 'node:util'

const exec = promisify(execFile)
const timeout = 15_000

async function command(file, args) {
  const { stdout } = await exec(file, args, { timeout, maxBuffer: 2 * 1024 * 1024, encoding: 'utf8' })
  return stdout
}

const quote = (value) => `'${String(value).replaceAll("'", "'\\''")}'`

export async function readAws(host = process.env.AWS_SSH_HOST) {
  if (!host) throw new Error('AWS_SSH_HOST가 설정되지 않았습니다.')
  if (!/^[\w.@-]+$/.test(host)) throw new Error('AWS_SSH_HOST 형식이 올바르지 않습니다.')
  const remote = async (args) => command('ssh', ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', host, args.map(quote).join(' ')])
  const [ps, stats] = await Promise.all([
    remote(['docker', 'ps', '-a', '--format', '{{json .}}']),
    remote(['docker', 'stats', '--no-stream', '--format', '{{json .}}']).catch(() => ''),
  ])
  const rows = (output) => output.split('\n').filter(Boolean).map((line) => JSON.parse(line))
  const byId = new Map(rows(stats).map((item) => [item.Container, item]))
  return rows(ps).map((item) => {
    const stat = [...byId].find(([id]) => id.startsWith(item.ID) || item.ID.startsWith(id))?.[1]
    return { id: item.ID, name: item.Names, image: item.Image, state: item.State, status: item.Status, cpu: stat?.CPUPerc || null, memory: stat?.MemPerc || null }
  })
}

async function gcloud(args) {
  return JSON.parse(await command('gcloud', args))
}

export async function readGcp({ project = process.env.GCP_PROJECT, region = process.env.GCP_REGION || 'asia-northeast3' } = {}) {
  if (!project) throw new Error('GCP_PROJECT가 설정되지 않았습니다.')
  const services = await gcloud(['run', 'services', 'list', '--platform=managed', `--project=${project}`, `--region=${region}`, '--format=json'])
  const end = new Date()
  const start = new Date(end.getTime() - 60 * 60 * 1000)
  const interval = `startTime=${start.toISOString()},endTime=${end.toISOString()}`
  const metrics = async (metric) => gcloud([
    'monitoring', 'time-series', 'list', `--project=${project}`,
    `--filter=metric.type="run.googleapis.com/${metric}" AND resource.type="cloud_run_revision"`,
    `--interval=${interval}`, '--format=json',
  ])
  const [requests, latencies] = await Promise.all([metrics('request_count'), metrics('request_latencies')])
  const byService = new Map()
  for (const series of requests) {
    const name = series.resource?.labels?.service_name
    if (!name) continue
    const row = byService.get(name) || { requests: 0, errors: 0 }
    for (const point of series.points || []) {
      const value = Number(point.value?.int64Value || point.value?.doubleValue || 0)
      row.requests += value
      if (/5xx/i.test(series.metric?.labels?.response_code_class || '')) row.errors += value
    }
    byService.set(name, row)
  }
  for (const series of latencies) {
    const row = byService.get(series.resource?.labels?.service_name)
    if (row) row.latencyMs = Math.round(Number(series.points?.[0]?.value?.distributionValue?.mean || 0))
  }
  const logs = await Promise.all(services.map(async (service) => {
    const name = service.metadata?.name
    if (!/^[a-z][a-z0-9-]{0,62}$/.test(name || '')) return [name, []]
    try {
      const entries = await gcloud(['logging', 'read', `resource.type="cloud_run_revision" AND resource.labels.service_name="${name}"`, '--limit=10', '--freshness=1h', '--format=json', `--project=${project}`])
      return [name, entries]
    } catch { return [name, []] }
  }))
  const logsByService = new Map(logs)
  return services.map((service) => {
    const name = service.metadata?.name
    const metric = byService.get(name) || { requests: 0, errors: 0, latencyMs: null }
    return {
      name,
      region: service.metadata?.labels?.['cloud.googleapis.com/location'] || region,
      url: service.status?.url || '',
      ready: service.status?.conditions?.find((condition) => condition.type === 'Ready')?.status === 'True',
      requests: metric.requests,
      latencyMs: metric.latencyMs ?? null,
      errorRate: metric.requests ? metric.errors / metric.requests : 0,
      logs: (logsByService.get(name) || []).map((entry) => ({ time: entry.timestamp, severity: entry.severity, message: entry.textPayload || entry.jsonPayload?.message || '' })),
    }
  })
}

export async function readActualCosts(cloud) {
  if (cloud === 'aws') {
    const from = new Date(); from.setUTCDate(1)
    const to = new Date(); to.setUTCDate(to.getUTCDate() + 1)
    return JSON.parse(await command('aws', ['ce', 'get-cost-and-usage', '--time-period', `Start=${from.toISOString().slice(0, 10)},End=${to.toISOString().slice(0, 10)}`, '--granularity', 'MONTHLY', '--metrics', 'UnblendedCost', '--group-by', 'Type=DIMENSION,Key=SERVICE', 'Type=DIMENSION,Key=USAGE_TYPE', '--output', 'json']))
  }
  const table = process.env.GCP_BILLING_TABLE
  if (!table || !/^[\w.-]+\.[\w$-]+\.[\w$-]+$/.test(table)) throw new Error('GCP_BILLING_TABLE이 설정되지 않았습니다.')
  const query = `SELECT service.description AS service, sku.description AS sku, SUM(cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS usd FROM \`${table}\` WHERE usage_start_time >= TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), MONTH) AND currency = 'USD' GROUP BY service, sku ORDER BY service, sku`
  return JSON.parse(await command('bq', ['query', '--use_legacy_sql=false', '--format=json', query]))
}

