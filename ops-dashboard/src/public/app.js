const $ = (selector) => document.querySelector(selector)
const status = $('#status')
const number = (value, digits = 0) => Number.isFinite(Number(value)) ? Number(value).toLocaleString('ko-KR', { maximumFractionDigits: digits }) : '—'
const money = (usd, rate) => `$${number(usd, 2)} · ₩${number(usd * rate)}`

function card(title, state, details = []) {
  const section = document.createElement('section')
  section.className = 'panel cloud-card'
  const header = document.createElement('div')
  header.className = 'panel-head'
  const heading = document.createElement('h2')
  heading.textContent = title
  const badge = document.createElement('span')
  badge.className = `connection-badge ${state.connected ? 'is-online' : 'is-offline'}`
  badge.textContent = state.connected ? '연결됨' : '미연결'
  header.append(heading, badge)
  section.append(header)
  if (!state.connected) {
    const note = document.createElement('p')
    note.className = 'empty'
    note.textContent = state.error || '자격 증명을 설정하면 데이터를 표시합니다.'
    section.append(note)
    return section
  }
  if (!details.length) {
    const note = document.createElement('p')
    note.className = 'empty'
    note.textContent = '표시할 항목이 없습니다.'
    section.append(note)
  } else section.append(...details)
  return section
}

function renderClouds(data) {
  const awsRows = (data.aws.containers || []).map((item) => {
    const row = document.createElement('article')
    row.className = 'data-row'
    const text = document.createElement('div')
    const name = document.createElement('strong')
    name.textContent = item.name
    const meta = document.createElement('small')
    meta.textContent = `${item.image} · ${item.status}`
    text.append(name, meta)
    const state = document.createElement('span')
    state.className = `state-label ${item.state === 'running' ? 'good' : 'bad'}`
    state.textContent = item.state
    const stats = document.createElement('small')
    stats.className = 'row-stats'
    stats.textContent = `CPU ${item.cpu || '—'} · 메모리 ${item.memory || '—'}`
    row.append(text, state, stats)
    return row
  })
  const gcpRows = (data.gcp.services || []).map((service) => {
    const section = document.createElement('article')
    section.className = 'service-block'
    const row = document.createElement('div')
    row.className = 'data-row'
    const text = document.createElement('div')
    const name = document.createElement('strong')
    name.textContent = service.name
    const meta = document.createElement('small')
    meta.textContent = service.region
    text.append(name, meta)
    const ready = document.createElement('span')
    ready.className = `state-label ${service.ready ? 'good' : 'bad'}`
    ready.textContent = service.ready ? '정상' : '비정상'
    const metrics = document.createElement('small')
    metrics.className = 'row-stats'
    metrics.textContent = `최근 1시간 · 요청 ${number(service.requests)} · 지연 ${service.latencyMs == null ? '—' : `${number(service.latencyMs)} ms`} · 오류율 ${(Number(service.errorRate || 0) * 100).toFixed(2)}%`
    row.append(text, ready, metrics)
    section.append(row)
    const logs = document.createElement('details')
    logs.className = 'recent-logs'
    const summary = document.createElement('summary')
    summary.textContent = '최근 로그'
    logs.append(summary)
    for (const entry of service.logs || []) {
      const line = document.createElement('p')
      line.textContent = `${entry.time || ''} ${entry.severity || ''} ${entry.message || ''}`
      logs.append(line)
    }
    section.append(logs)
    return section
  })
  $('#cloud-grid').replaceChildren(
    card('AWS · Lightsail Docker', data.aws, awsRows),
    card('GCP · Cloud Run', data.gcp, gcpRows),
  )
  $('#updated-at').textContent = data.updatedAt ? new Date(data.updatedAt).toLocaleTimeString('ko-KR') : '--:--:--'
}

function entriesFor(cloud, raw) {
  if (cloud === 'aws') return (raw?.ResultsByTime || []).flatMap((period) => period.Groups || []).map((group) => ({
    service: group.Keys.join(' · '), usd: Number(group.Metrics?.UnblendedCost?.Amount || 0),
  }))
  return Array.isArray(raw) ? raw.map((row) => ({ service: `${row.service} · ${row.sku}`, usd: Number(row.usd || 0) })) : []
}

function renderCosts(data) {
  const note = `USD/KRW ${number(data.usdKrw)} · 공시 가격 기준일 ${data.priceDate}. 예상은 무료 구간·세금·네트워크 비용을 제외한 기준 사용량입니다.`
  $('#cost-note').textContent = note
  $('#cost-grid').replaceChildren(...['aws', 'gcp'].map((cloud) => {
    const isActual = Boolean(data.actual?.[cloud])
    const rows = isActual ? entriesFor(cloud, data.actual[cloud]) : data.estimates.filter((item) => item.cloud === cloud)
    const children = rows.map((item) => {
      const row = document.createElement('article')
      row.className = 'data-row'
      const label = document.createElement('strong')
      label.textContent = item.service
      const value = document.createElement('span')
      value.className = 'cost-value'
      value.textContent = money(item.usd, data.usdKrw)
      row.append(label, value)
      return row
    })
    const total = rows.reduce((sum, item) => sum + item.usd, 0)
    const heading = document.createElement('p')
    heading.className = 'cost-total'
    heading.textContent = `${isActual ? '실제' : '예상'} · 월 합계 ${money(total, data.usdKrw)}`
    return card(cloud === 'aws' ? 'AWS' : 'GCP', { connected: true }, [heading, ...children])
  }))
}

async function refresh() {
  $('#refresh').disabled = true
  status.textContent = '클라우드 정보를 갱신하고 있습니다.'
  try {
    const response = await fetch('/api/refresh', { method: 'POST', cache: 'no-store' })
    renderClouds(await response.json())
    status.textContent = '클라우드 정보가 갱신됐습니다.'
  } catch {
    status.textContent = '클라우드 정보를 갱신하지 못했습니다.'
  } finally { $('#refresh').disabled = false }
}

async function loadCosts() {
  try {
    const response = await fetch('/api/costs', { cache: 'no-store' })
    renderCosts(await response.json())
  } catch { status.textContent = '비용 정보를 불러오지 못했습니다.' }
}

function selectTab(tab) {
  const costs = tab === 'costs'
  $('#clouds-view').hidden = costs
  $('#costs-view').hidden = !costs
  $('#page-title').textContent = costs ? '월 비용' : '클라우드 상태'
  document.querySelectorAll('[data-tab]').forEach((link) => {
    const selected = link.dataset.tab === tab
    link.classList.toggle('active', selected)
    if (selected) link.setAttribute('aria-current', 'page')
    else link.removeAttribute('aria-current')
  })
  if (costs) void loadCosts()
}

$('#refresh').addEventListener('click', () => void refresh())
document.querySelectorAll('[data-tab]').forEach((link) => link.addEventListener('click', () => selectTab(link.dataset.tab)))
window.addEventListener('hashchange', () => selectTab(location.hash === '#costs' ? 'costs' : 'clouds'))
selectTab(location.hash === '#costs' ? 'costs' : 'clouds')
void refresh()
setInterval(() => { if (location.hash !== '#costs') void refresh() }, 30_000)
