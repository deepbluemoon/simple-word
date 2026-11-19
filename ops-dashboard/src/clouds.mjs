import { execFile } from 'node:child_process'
import { promisify } from 'node:util'

const exec = promisify(execFile)
const timeout = 15_000

async function command(file, args) {
  const { stdout } = await exec(file, args, { timeout, maxBuffer: 2 * 1024 * 1024, encoding: 'utf8' })
  return stdout
}

const quote = (value) => `'${String(value).replaceAll("'", "'\\''")}'`
const jsonLines = (output) => output.split('\n').filter(Boolean).map((line) => JSON.parse(line))
const dockerLabels = (value = '') => Object.fromEntries(String(value).split(',').filter(Boolean).map((part) => {
  const index = part.indexOf('=')
  return index < 0 ? [part, ''] : [part.slice(0, index), part.slice(index + 1)]
}))
const metricValue = (point) => Number(point?.value?.doubleValue ?? point?.value?.int64Value ?? point?.value?.distributionValue?.mean ?? 0)

export function normalizeDockerOutput(psOutput, statsOutput, serverName) {
  const stats = new Map(jsonLines(statsOutput).map((row) => [row.Container, row]))
  const projects = new Map()
  for (const row of jsonLines(psOutput)) {
    const labels = dockerLabels(row.Labels)
    const project = labels['com.docker.compose.project'] || 'Docker containers'
    const service = labels['com.docker.compose.service'] || row.Names
    const group = projects.get(project) || { name: project, containers: [] }
    const stat = [...stats].find(([id]) => id.startsWith(row.ID) || row.ID.startsWith(id))?.[1]
    const health = row.Status?.match(/\((healthy|unhealthy|health: starting)\)/i)?.[1] || row.State
    group.containers.push({
      id: row.ID,
      name: row.Names,
      role: service,
      service,
      image: row.Image,
      state: row.State,
      health,
      cpu: stat?.CPUPerc || null,
      memory: stat?.MemPerc || null,
    })
    projects.set(project, group)
  }
  return [{ name: serverName, services: [...projects.values()] }]
}

export async function readAws(host = process.env.AWS_SSH_HOST) {
  if (!host) throw new Error('AWS_SSH_HOST가 설정되지 않았습니다.')
  if (!/^[\w.@-]+$/.test(host)) throw new Error('AWS_SSH_HOST 형식이 올바르지 않습니다.')
  const remote = async (args) => command('ssh', ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', host, args.map(quote).join(' ')])
  const [ps, stats] = await Promise.all([
    remote(['docker', 'ps', '-a', '--format', '{{json .}}']),
    remote(['docker', 'stats', '--no-stream', '--format', '{{json .}}']).catch(() => ''),
  ])
  return normalizeDockerOutput(ps, stats, host)
}

async function gcloud(args) {
  return JSON.parse(await command('gcloud', args))
}

function utilization(series = []) {
  const values = series.flatMap((row) => (row.points || []).slice(0, 1).map(metricValue)).filter(Number.isFinite)
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length * 100 : null
}

const readyCondition = (revision) => revision.status?.conditions?.find((item) => item.type === 'Ready')?.status === 'True'
const roleForRevision = (name, tags = []) => /shadow/i.test(`${name} ${tags.join(' ')}`) ? 'shadow' : /canary/i.test(`${name} ${tags.join(' ')}`) ? 'canary' : 'service'

export function normalizeGcpServices(services, details = {}, revisions = {}, metrics = {}, region = '') {
  return services.map((service) => {
    const name = service.metadata?.name
    const detail = details[name] || service
    const traffic = detail.status?.traffic || []
    const revisionRows = revisions[name] || []
    const metricRows = metrics[name] || {}
    const trafficByRevision = new Map()
    for (const entry of traffic) {
      const revisionName = entry.revisionName || entry.revision
      if (revisionName) trafficByRevision.set(revisionName, { percent: Number(entry.percent || 0), tag: entry.tag || '' })
    }
    const minInstances = Number(detail.spec?.template?.metadata?.annotations?.['autoscaling.knative.dev/minScale'] ?? detail.spec?.template?.scaling?.minInstanceCount ?? detail.spec?.scaling?.minInstanceCount ?? 0)
    const maxRaw = detail.spec?.template?.metadata?.annotations?.['autoscaling.knative.dev/maxScale'] ?? detail.spec?.template?.scaling?.maxInstanceCount ?? detail.spec?.scaling?.maxInstanceCount
    const rows = revisionRows.map((revision) => {
      const revisionName = revision.metadata?.name
      const labels = revision.metadata?.labels || {}
      const role = roleForRevision(revisionName, [trafficByRevision.get(revisionName)?.tag, labels['run.googleapis.com/traffic-tag']].filter(Boolean))
      const matching = (metricRows.instanceCount || []).filter((row) => row.resource?.labels?.revision_name === revisionName)
      const instances = matching.reduce((sum, row) => sum + (row.points || []).slice(0, 1).reduce((pointSum, point) => pointSum + metricValue(point), 0), 0)
      const perRevision = Object.fromEntries(['cpuUtilization', 'memoryUtilization'].map((key) => [key, utilization((metricRows[key] || []).filter((row) => row.resource?.labels?.revision_name === revisionName))]))
      return {
        name: revisionName,
        role,
        image: revision.spec?.containers?.[0]?.image || '',
        ready: readyCondition(revision),
        createdAt: revision.metadata?.creationTimestamp || null,
        trafficPercent: trafficByRevision.get(revisionName)?.percent || 0,
        instances: matching.length ? instances : null,
        ...perRevision,
      }
    })
    return {
      name,
      region: service.metadata?.labels?.['cloud.googleapis.com/location'] || region,
      url: detail.status?.url || '',
      ready: detail.status?.conditions?.find((condition) => condition.type === 'Ready')?.status === 'True',
      minInstances: Number.isFinite(minInstances) ? minInstances : 0,
      maxInstances: maxRaw == null ? null : Number(maxRaw),
      revisions: rows,
    }
  })
}

export async function readGcp({ project = process.env.GCP_PROJECT, region = process.env.GCP_REGION || 'asia-northeast3' } = {}) {
  if (!project) throw new Error('GCP_PROJECT가 설정되지 않았습니다.')
  const services = await gcloud(['run', 'services', 'list', '--platform=managed', `--project=${project}`, `--region=${region}`, '--format=json'])
  const end = new Date()
  const start = new Date(end.getTime() - 5 * 60 * 1000)
  const interval = `startTime=${start.toISOString()},endTime=${end.toISOString()}`
  const serviceData = await Promise.all(services.map(async (service) => {
    const name = service.metadata?.name
    if (!/^[a-z][a-z0-9-]{0,62}$/.test(name || '')) return [name, service, [], {}]
    const [detail, revisionRows] = await Promise.all([
      gcloud(['run', 'services', 'describe', name, '--platform=managed', `--project=${project}`, `--region=${region}`, '--format=json']),
      gcloud(['run', 'revisions', 'list', `--service=${name}`, '--platform=managed', `--project=${project}`, `--region=${region}`, '--format=json']),
    ])
    const metric = async (type) => gcloud([
      'monitoring', 'time-series', 'list', `--project=${project}`,
      `--filter=metric.type="run.googleapis.com/container/${type}" AND resource.type="cloud_run_revision" AND resource.labels.service_name="${name}"`,
      `--interval=${interval}`, '--format=json',
    ]).catch(() => [])
    const [instanceCount, cpuUtilization, memoryUtilization] = await Promise.all([metric('instance_count'), metric('cpu/utilizations'), metric('memory/utilizations')])
    return [name, detail, revisionRows, { instanceCount, cpuUtilization, memoryUtilization }]
  }))
  const details = Object.fromEntries(serviceData.map(([name, detail]) => [name, detail]))
  const revisions = Object.fromEntries(serviceData.map(([name, , rows]) => [name, rows]))
  const metrics = Object.fromEntries(serviceData.map(([name, , , values]) => [name, values]))
  const logs = await Promise.all(services.map(async (service) => {
    const name = service.metadata?.name
    if (!/^[a-z][a-z0-9-]{0,62}$/.test(name || '')) return [name, []]
    try {
      const entries = await gcloud(['logging', 'read', `resource.type="cloud_run_revision" AND resource.labels.service_name="${name}"`, '--limit=10', '--freshness=1h', '--format=json', `--project=${project}`])
      return [name, entries]
    } catch { return [name, []] }
  }))
  const result = normalizeGcpServices(services, details, revisions, metrics, region)
  for (const service of result) service.logs = (logs.find(([name]) => name === service.name)?.[1] || []).map((entry) => ({ time: entry.timestamp, severity: entry.severity, message: entry.textPayload || entry.jsonPayload?.message || '' }))
  return result
}

export async function readLocalDocker() {
  const [ps, stats] = await Promise.all([
    command('docker', ['ps', '-a', '--format', '{{json .}}']),
    command('docker', ['stats', '--no-stream', '--format', '{{json .}}']).catch(() => ''),
  ])
  return normalizeDockerOutput(ps, stats, '개발용 Docker')
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

