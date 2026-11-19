const $ = (id) => document.getElementById(id)
const number = (value, digits = 0) => Number.isFinite(Number(value)) ? Number(value).toLocaleString('ko-KR', { maximumFractionDigits: digits }) : '—'
const money = (usd, rate) => `$${number(usd, 2)} · ₩${number(usd * rate)}`

function line(label, value) {
  const row = document.createElement('div')
  row.className = 'cloud-line'
  const name = document.createElement('span')
  name.textContent = label
  const content = document.createElement('span')
  content.textContent = value
  row.append(name, content)
  return row
}

function badge(text, kind = '') {
  const node = document.createElement('span')
  node.className = `cloud-role${kind ? ` is-${kind}` : ''}`
  node.textContent = text
  return node
}

function group(title, caption, rows) {
  const section = document.createElement('section')
  section.className = 'cloud-service'
  const heading = document.createElement('div')
  heading.className = 'cloud-service-head'
  const name = document.createElement('strong')
  name.textContent = title
  heading.append(name)
  if (caption) {
    const note = document.createElement('span')
    note.textContent = caption
    heading.append(note)
  }
  section.append(heading, ...rows)
  return section
}

function dockerServer(server) {
  const services = (server.services || []).map((service) => group(service.name, '', (service.containers || []).map((container) => {
    const details = document.createElement('div')
    details.className = 'cloud-runtime-row'
    const main = document.createElement('div')
    main.className = 'cloud-runtime-name'
    main.append(badge(container.role || container.service || 'container', container.role || 'service'))
    const name = document.createElement('strong')
    name.textContent = container.name
    main.append(name)
    const image = document.createElement('small')
    image.textContent = container.image || '이미지 없음'
    const status = document.createElement('small')
    status.textContent = `${container.health || container.state || '상태 미상'} · CPU ${container.cpu || '—'} · 메모리 ${container.memory || '—'}`
    details.append(main, image, status)
    return details
  })))
  return group(server.name, '', services)
}

function gcpService(service) {
  const revisions = (service.revisions || []).map((revision) => {
    const row = document.createElement('div')
    row.className = 'cloud-runtime-row'
    const name = document.createElement('div')
    name.className = 'cloud-runtime-name'
    name.append(badge(revision.role === 'canary' ? '카나리' : revision.role === 'shadow' ? '섀도' : '서비스', revision.role))
    const revisionName = document.createElement('strong')
    revisionName.textContent = revision.name
    name.append(revisionName)
    const info = document.createElement('small')
    const created = revision.createdAt ? new Date(revision.createdAt).toLocaleString('ko-KR') : '생성 시각 —'
    info.textContent = `${revision.ready ? '정상' : '준비 안 됨'} · 생성 ${created} · 트래픽 ${number(revision.trafficPercent, 1)}% · 인스턴스 ${revision.instances == null ? '—' : number(revision.instances)} · CPU ${revision.cpuUtilization == null ? '—' : `${number(revision.cpuUtilization, 1)}%`} · 메모리 ${revision.memoryUtilization == null ? '—' : `${number(revision.memoryUtilization, 1)}%`}`
    const image = document.createElement('small')
    image.textContent = revision.image || '이미지 없음'
    row.append(name, info, image)
    return row
  })
  return group(`${service.name} · ${service.region}`, `최소 ${number(service.minInstances)} / 최대 ${service.maxInstances == null ? '미설정' : number(service.maxInstances)} 인스턴스`, revisions)
}

function cloudCard(title, status, rows) {
  const card = document.createElement('section')
  card.className = 'cloud-card'
  const heading = document.createElement('div')
  heading.className = 'panel-head'
  const name = document.createElement('h3')
  name.textContent = title
  const badge = document.createElement('span')
  badge.className = `cloud-state${status.connected ? '' : ' is-offline'}`
  badge.textContent = status.connected ? '연결됨' : '미연결'
  heading.append(name, badge)
  card.append(heading)
  if (!status.connected) {
    const error = document.createElement('p')
    error.textContent = status.error || '자격 증명을 설정하면 상태를 확인합니다.'
    card.append(error)
  } else if (rows.length) card.append(...rows)
  else {
    const empty = document.createElement('p')
    empty.textContent = '표시할 항목이 없습니다.'
    card.append(empty)
  }
  return card
}

function renderClouds(data) {
  const aws = (data.aws.servers || []).map(dockerServer)
  const gcp = (data.gcp.services || []).map(gcpService)
  const local = (data.local.servers || []).map(dockerServer)
  $('cloud-grid').replaceChildren(cloudCard('AWS Lightsail', data.aws, aws), cloudCard('GCP Cloud Run', data.gcp, gcp), cloudCard('로컬 Docker', data.local, local))
}

function costRows(cloud, data) {
  const raw = data.actual?.[cloud]
  if (cloud === 'aws' && raw?.ResultsByTime) return raw.ResultsByTime.flatMap((period) => period.Groups || []).map((group) => ({ label: group.Keys.join(' · '), usd: Number(group.Metrics?.UnblendedCost?.Amount || 0) }))
  if (cloud === 'gcp' && Array.isArray(raw)) return raw.map((row) => ({ label: `${row.service} · ${row.sku}`, usd: Number(row.usd || 0) }))
  return data.estimates.filter((item) => item.cloud === cloud).map((item) => ({ label: item.service, usd: Number(item.usd || 0) }))
}

function renderCosts(data) {
  $('cost-note').textContent = `USD/KRW ${number(data.usdKrw)} · 기준일 ${data.priceDate}. 실제 비용이 없으면 공시 가격 기반 예상입니다.`
  $('cost-grid').replaceChildren(...['aws', 'gcp'].map((cloud) => {
    const rows = costRows(cloud, data)
    const actual = Boolean(data.actual?.[cloud])
    const content = rows.map((item) => line(item.label, money(item.usd, data.usdKrw)))
    const total = rows.reduce((sum, item) => sum + item.usd, 0)
    content.unshift(line(actual ? '실제 월 합계' : '예상 월 합계', money(total, data.usdKrw)))
    return cloudCard(cloud === 'aws' ? 'AWS 비용' : 'GCP 비용', { connected: true }, content)
  }))
}

async function refresh() {
  const response = await fetch('/api/refresh', { method: 'POST', cache: 'no-store' })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  renderClouds(await response.json())
}

async function loadCosts() {
  try {
    const response = await fetch('/api/costs', { cache: 'no-store' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    renderCosts(await response.json())
  } catch {
    $('cost-grid').replaceChildren(cloudCard('월 비용', { connected: false, error: '비용 정보를 불러오지 못했습니다.' }, []))
  }
}

$('cloud-refresh').addEventListener('click', () => { void refresh().catch(() => {}) })
void refresh().catch(() => {})
void loadCosts()
setInterval(() => { void refresh().catch(() => {}) }, 30_000)
