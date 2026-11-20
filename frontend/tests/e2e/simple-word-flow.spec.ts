import { expect, test } from '@playwright/test'

test('CSP allows Vue scripts and dynamic inline styles', async ({ page }) => {
  const policy = "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; connect-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; font-src 'self' https://cdn.jsdelivr.net"
  await page.addInitScript(() => {
    window.addEventListener('securitypolicyviolation', (event) => {
      const root = document.documentElement
      const previous = root.getAttribute('data-csp-violations') ?? ''
      root.setAttribute('data-csp-violations', `${previous}${event.violatedDirective}:${event.blockedURI};`)
    })
  })
  await page.route('**/', async (route) => {
    if (new URL(route.request().url()).pathname !== '/') return route.continue()
    const response = await route.fetch()
    await route.fulfill({ response, headers: { ...response.headers(), 'content-security-policy': policy } })
  })
  await page.route('**/simplify', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 500))
    await route.fulfill({ json: { model_version: 'e2e', sentences: [{ original: '안내 문장입니다.', simple: '안내 문장입니다.', fallback: false, paragraph_id: 0 }] } })
  })
  const response = await page.goto('/')
  expect(response?.headers()['content-security-policy']).toBe(policy)
  await page.getByRole('button', { name: '글 붙여넣기' }).click()
  await page.getByRole('textbox', { name: '쉬운 말로 바꿀 공문서 내용' }).fill('안내 문장입니다.')
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByRole('progressbar', { name: '문서 처리 진행률' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '쉬운 말로 바꾼 결과' })).toBeVisible()
  expect(await page.locator('html').getAttribute('data-csp-violations')).toBeNull()
})

test('uploads a public document, sends sentence feedback, and restores the result after reload', async ({ page }) => {
  await page.route('**/simplify', (route) => route.fulfill({ json: { model_version: 'e2e', sentences: [
    { original: '신청서는 제출해야 합니다.', simple: '신청서는 내야 합니다.', fallback: false, paragraph: 0, paragraph_id: 0 },
    { original: '수수료는 400원입니다.', simple: '수수료는 400원입니다.', fallback: true, fallback_reason: 'numbers', paragraph: 1, paragraph_id: 1 },
  ] } }))
  await page.route('**/feedback', (route) => route.fulfill({ json: { saved: true } }))
  await page.goto('/')
  await page.locator('input[type=file]').setInputFiles({
    name: '주민 안내문.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('신청은 2026년 12월 31일까지 해야 합니다.\n수수료는 400원입니다.'),
  })
  await expect(page.getByText('주민 안내문.txt')).toBeVisible()
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByRole('heading', { name: '쉬운 말로 바꾼 결과' })).toBeVisible()
  await expect(page.getByRole('navigation', { name: '진행 단계' })).toContainText('문장 나누기 완료')
  await expect(page.getByRole('tab', { name: '문서 보기' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.document-paragraph')).toHaveCount(2)
  await expect(page.locator('.document-sentence mark')).toContainText('내야')
  await page.getByRole('tab', { name: '문장별 보기' }).click()
  await expect(page.locator('#sentences-panel').getByText(/개 문장에서 말이 바뀌었어요/)).toBeVisible()
  await page.getByRole('tab', { name: '문서 보기' }).click()
  const fallbackSentence = page.locator('.document-sentence').nth(1)
  await fallbackSentence.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('.clause-note')).toContainText('수수료는 400원입니다.')
  await expect(page.locator('.clause-note')).toContainText('숫자나 날짜를 안전하게 지키려고 원문을 유지했어요.')
  await page.getByRole('button', { name: /좋아요/ }).first().click()
  await expect(page.getByText('의견 감사합니다.')).toBeVisible()
  const resultUrl = page.url()
  await page.reload()
  expect(page.url()).toBe(resultUrl)
  await expect(page.getByRole('heading', { name: '쉬운 말로 바꾼 결과' })).toBeVisible()
  await expect(page.getByText('주민 안내문.txt')).toBeVisible()
})

test('accepts pasted text and keeps reading controls usable at 400px', async ({ page }) => {
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.setViewportSize({ width: 400, height: 800 })
  await page.goto('/')
  await page.getByRole('button', { name: '글 붙여넣기' }).click()
  await page.getByRole('textbox', { name: '쉬운 말로 바꿀 공문서 내용' }).fill('첫 문장은 2026년 12월 31일까지 신청해야 합니다.\n\n다음 안내는 400원입니다.')
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByRole('heading', { name: '쉬운 말로 바꾼 결과' })).toBeVisible()
  await page.getByRole('button', { name: '쉬운 말 복사' }).click()
  await expect(page.getByRole('status').filter({ hasText: '쉬운 말을 복사했어요.' })).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('첫 문장은')
  const [easyDownload] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: '쉬운 말 .txt', exact: true }).click()])
  expect(easyDownload.suggestedFilename()).toBe('붙여넣은 공문서-쉬운말.txt')
  const [comparisonDownload] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: '원문·쉬운 말 .txt' }).click()])
  expect(comparisonDownload.suggestedFilename()).toBe('붙여넣은 공문서-원문-쉬운말.txt')
  await page.getByRole('tab', { name: '문장별 보기' }).click()
  await expect(page.locator('#sentences-panel .sentence-card')).toHaveCount(2)
  await page.getByRole('button', { name: '글자 크게' }).click()
  await expect(page.getByRole('button', { name: '글자 크게' })).toHaveAttribute('aria-pressed', 'true')
  await page.reload()
  await expect(page.getByRole('button', { name: '글자 크게' })).toHaveAttribute('aria-pressed', 'true')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('shows a retry countdown after 429 and retries successfully', async ({ page }) => {
  let attempts = 0
  await page.route('**/simplify', async (route) => {
    attempts++
    if (attempts === 1) {
      await route.fulfill({ status: 429, headers: { 'Retry-After': '3' }, body: 'busy' })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ model_version: 'dummy', sentences: [{ original: '신청 안내입니다.', simple: '신청 안내입니다.', fallback: false }] }),
    })
  })
  await page.goto('/')
  await page.locator('input[type=file]').setInputFiles({
    name: '안내.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('신청 안내입니다.'),
  })
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByRole('status').filter({ hasText: '3초 뒤 자동으로 다시 시도해요.' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '쉬운 말로 바꾼 결과' })).toBeVisible({ timeout: 10_000 })
  expect(attempts).toBe(2)
})

test('explains the 5 MB file limit', async ({ page }) => {
  await page.goto('/')
  await page.locator('input[type=file]').setInputFiles({
    name: '큰 안내.txt',
    mimeType: 'text/plain',
    buffer: Buffer.alloc(5 * 1024 * 1024 + 1, 65),
  })
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByRole('alert')).toHaveText('파일은 5MB 이하여야 해요.')
})

test('explains unsupported file types', async ({ page }) => {
  await page.goto('/')
  await page.locator('input[type=file]').setInputFiles({
    name: '안내.png',
    mimeType: 'image/png',
    buffer: Buffer.from('not a supported document'),
  })
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByRole('alert')).toHaveText('TXT, DOCX, HWPX, PDF 파일을 올려 주세요.')
})

test('explains the 100-sentence limit', async ({ page }) => {
  const sentences = Array.from({ length: 101 }, (_, index) => `안내 문장 ${index + 1}입니다.`).join('\n')
  await page.goto('/')
  await page.getByRole('button', { name: '글 붙여넣기' }).click()
  await page.getByRole('textbox', { name: '쉬운 말로 바꿀 공문서 내용' }).fill(sentences)
  await page.getByRole('button', { name: '쉬운 말로 바꾸기' }).click()
  await expect(page.getByRole('alert')).toHaveText('공문서는 한 번에 100문장까지 바꿀 수 있어요. 파일을 나눠서 올려 주세요.')
})
